// Hopper submissions — the list behind /hoppers and /admin/hoppers.
//
// Anyone can propose the URL of a public blyg hopper (`{mount}h/{slug}/`) for
// the World Machines blyg at blyg.worldmachines.org. A submission that
// validates as a real public blyg hopper (validateHopper below) is accepted
// at once (status `approved`); anything else is refused with a reason. The
// admin can still reject (and so block) an accepted hopper later. Records left
// `pending` by the old approve-first flow can be approved by hand or
// re-validated from /admin/hoppers.
//
// Accepting only records the hopper: stock blygger (v0.46) cannot subscribe to
// a hopper — it is an HTML page with no feed, and POST /api/subscriptions on
// its URL would resolve to the member's WHOLE blyg. Polling + filing waits for
// hopper feeds (blygger-spec Fable queue item 14; manifest `hoppers[]` is
// proposed in blygger-spec#18 — see matchManifestHoppers).
//
// KV layout (binding HOPPERS — its own namespace, because HANDLES is listed
// whole by /api/contributors, /api/admin/handles and provision-access.mjs):
//
//   sub:<id>             submission record (see createSubmission)
//   canon:<canonical>    id of the live (pending/approved) submission for a URL
//   block:blyg:<base>    id of the rejection that blocked this blyg
//   block:email:<email>  id of the rejection that blocked this submitter
//
// Canonical URLs and bases end in "/". Records written before auto-accept
// stored both without the trailing slash; lookups below check both spellings.
//
// A rejection blocks the submitter's email AND their whole blyg (identity
// origin), not just the one hopper URL — otherwise "may not re-submit" is one
// new slug away. The email is self-reported (the form is public, like /join),
// so the blyg block is the one that actually holds.

export const SUB = 'sub:';
const CANON = 'canon:';
const BLOCK_BLYG = 'block:blyg:';
const BLOCK_EMAIL = 'block:email:';

/** `decided_by` on records the validator accepted. */
export const AUTO_APPROVER = 'auto-validator';

const FETCH_TIMEOUT_MS = 8000;    // per request
const VALIDATE_BUDGET_MS = 25000; // whole validation, all requests
const MAX_REDIRECTS = 5;
const MAX_HTML_CHARS = 300000;
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,79}$/;
const USER_AGENT = 'worldmachines-hoppers (+https://worldmachines.org/hoppers)';

// ── Validation ───────────────────────────────────────────────────────────────
// Blyg protocol v0.4 has no hopper surface yet, so this is the best check
// available (algorithm from the blygger-spec maintainers; modelled on
// blygger-studio src/importer/resolve.ts, not vendored):
//   1. normalize the URL (https, no query/fragment, ends /h/{slug}/)
//   2. the page answers 200 HTML (Studio 404s private/unknown hoppers)
//   3. resolve the blyg manifest: rel="blyg" link → mount → /blyg/ → /
//   4. identity origin = manifest's final URL minus its last segment
//   5. the final page URL is exactly {identity}h/{slug}/ (catches soft-404s)
//   7. if the manifest lists hoppers[], the page must be one of them

/** Strip query + fragment, ensure a trailing "/". */
function normalizeLoose(raw) {
  const u = new URL(raw);
  u.search = '';
  u.hash = '';
  if (!u.pathname.endsWith('/')) u.pathname += '/';
  return u.toString();
}

/**
 * Step 1. Normalize a submitted hopper URL.
 * @returns {{canonical:string, slug:string, mount:string}|{error:string}}
 */
export function normalizeHopperUrl(raw) {
  let url;
  try {
    url = new URL(String(raw || '').trim());
  } catch {
    return { error: 'That is not a valid URL.' };
  }
  if (url.protocol === 'http:') return { error: 'Hopper URLs must use https, not http.' };
  if (url.protocol !== 'https:') return { error: 'Hopper URLs must be https.' };
  if (url.username || url.password) return { error: 'Hopper URLs cannot contain a username or password.' };
  const canonical = normalizeLoose(url.toString());
  const { pathname, origin } = new URL(canonical);
  const match = pathname.match(/^(.*\/)h\/([^/]+)\/$/);
  if (!match || !SLUG_RE.test(match[2])) {
    return {
      error: 'That does not look like a public hopper URL. It should end in /h/<hopper-name>/, ' +
        'where the name is lowercase letters, digits and hyphens.',
    };
  }
  return { canonical, slug: match[2], mount: origin + match[1] };
}

/**
 * fetch() that follows up to MAX_REDIRECTS hops by hand, so every hop is seen
 * (and must stay https). Every request carries a timeout, capped by the
 * overall validation deadline.
 * @returns {Promise<{res:Response, url:string}|{error:string, url:string}>}
 */
async function fetchFollow(url, ctx, accept) {
  let current = url;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const remaining = ctx.deadline - Date.now();
    if (remaining <= 0) return { error: 'timeout', url: current };
    let res;
    try {
      res = await ctx.fetchFn(current, {
        headers: { Accept: accept, 'User-Agent': USER_AGENT },
        redirect: 'manual',
        signal: AbortSignal.timeout(Math.min(ctx.timeoutMs, remaining)),
      });
    } catch (e) {
      return { error: e && e.name === 'TimeoutError' ? 'timeout' : 'unreachable', url: current };
    }
    const location = res.status >= 300 && res.status < 400 ? res.headers.get('location') : null;
    if (!location) return { res, url: current };
    await discard(res);
    let next;
    try {
      next = new URL(location, current);
    } catch {
      return { error: 'bad-redirect', url: current };
    }
    if (next.protocol !== 'https:') return { error: 'insecure-redirect', url: next.toString() };
    current = next.toString();
  }
  return { error: 'too-many-redirects', url: current };
}

async function discard(res) {
  try { await res.body?.cancel(); } catch { /* already consumed */ }
}

const FETCH_ERRORS = {
  timeout: 'That hopper took too long to answer. Try again in a minute.',
  unreachable: 'Could not reach that hopper. Is the blyg online?',
  'bad-redirect': 'That hopper redirects to an invalid URL.',
  'insecure-redirect': 'That hopper redirects to a non-https URL.',
  'too-many-redirects': `That hopper redirects more than ${MAX_REDIRECTS} times.`,
};

function isManifest(v) {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v) && typeof v.blyg === 'string';
}

/**
 * Fetch `url`; if the body parses as a JSON object with a string "blyg" key it
 * is a manifest (Content-Type is not trusted). Skips URLs already tried.
 * @returns {Promise<{manifest:object, manifestUrl:string}|null>}
 */
async function fetchManifestAt(url, ctx) {
  if (ctx.tried.includes(url)) return null;
  ctx.tried.push(url);
  const got = await fetchFollow(url, ctx, 'application/json, */*;q=0.5');
  if (got.error) return null;
  if (!got.res.ok) { await discard(got.res); return null; }
  let parsed;
  try { parsed = JSON.parse(await got.res.text()); } catch { return null; }
  if (!isManifest(parsed)) return null;
  const at = new URL(got.url);
  at.search = '';
  at.hash = '';
  return { manifest: parsed, manifestUrl: at.toString() };
}

/** Step 4: identity origin = the manifest's final URL minus its last segment. */
export function identityOf(manifestUrl) {
  const u = new URL(manifestUrl);
  u.pathname = u.pathname.replace(/[^/]*$/, '');
  u.search = '';
  u.hash = '';
  return u.toString();
}

/** Step 3: the first candidate that parses as a manifest wins. */
async function resolveManifest(html, pageUrl, slug, ctx) {
  const tryBase = (base) => fetchManifestAt(base + 'blyg.json', ctx);

  // a. <link rel="blyg" href>: the href itself, else the href as a base.
  const rel = findRelBlygHref(html);
  if (rel) {
    let href = null;
    try { href = new URL(rel, pageUrl).toString(); } catch { /* ignore a bad href */ }
    if (href) {
      const direct = await fetchManifestAt(href, ctx);
      if (direct) return direct;
      const viaBase = await tryBase(normalizeLoose(href));
      if (viaBase) return viaBase;
    }
  }

  // b. The mount: the final page URL before /h/{slug}/.
  const suffix = `h/${slug}/`;
  if (pageUrl.endsWith('/' + suffix)) {
    const found = await tryBase(pageUrl.slice(0, -suffix.length));
    if (found) return found;
  }

  // c. Conventional mounts on the final host.
  const { origin } = new URL(pageUrl);
  for (const base of [`${origin}/blyg/`, `${origin}/`]) {
    const found = await tryBase(base);
    if (found) return found;
  }
  return null;
}

/** Accept blyg protocol 0.1–0.4 (patch suffixes allowed). */
export function supportedBlygVersion(v) {
  return typeof v === 'string' && /^0\.[1-4](\.\d+)?$/.test(v.trim());
}

/**
 * Step 7 — future slot. blygger-spec#18 proposes a manifest key
 *   "hoppers": [{ "title", "page": "h/{slug}/", "feed": "h/{slug}/feed.xml" }]
 * If the manifest has it, the hopper page must be one of its entries (each
 * `page` resolved against the identity origin), and that entry's feed is kept.
 * Without the key there is nothing to check yet.
 * @returns {{listed:boolean, feed:string|null}|{error:string}}
 */
export function matchManifestHoppers(manifest, base, pageUrl) {
  if (!Array.isArray(manifest.hoppers)) return { listed: false, feed: null };
  for (const entry of manifest.hoppers) {
    if (!entry || typeof entry.page !== 'string') continue;
    let page;
    try { page = normalizeLoose(new URL(entry.page, base).toString()); } catch { continue; }
    if (page !== pageUrl) continue;
    let feed = null;
    if (typeof entry.feed === 'string') {
      try { feed = new URL(entry.feed, base).toString(); } catch { /* keep null */ }
    }
    return { listed: true, feed };
  }
  return { error: "This blyg lists its public hoppers in its manifest, and that hopper is not one of them." };
}

/**
 * Check that `raw` is a real, public blyg hopper.
 * @param {string} raw  submitted URL
 * @param {{fetchFn?:Function, timeoutMs?:number, budgetMs?:number}} [opts]
 * @returns {Promise<{ok:true, canonical, base, slug, title, blyg_title, generator,
 *   blyg_version, manifest_url, final_url, feed}|{error:string}>}
 */
export async function validateHopper(raw, opts = {}) {
  const norm = normalizeHopperUrl(raw);
  if (norm.error) return norm;
  const { canonical, slug } = norm;
  const ctx = {
    fetchFn: opts.fetchFn || ((url, init) => fetch(url, init)),
    timeoutMs: opts.timeoutMs ?? FETCH_TIMEOUT_MS,
    deadline: Date.now() + (opts.budgetMs ?? VALIDATE_BUDGET_MS),
    tried: [],
  };

  // 2. The hopper page: 200 + HTML.
  const page = await fetchFollow(canonical, ctx, 'text/html');
  if (page.error) return { error: FETCH_ERRORS[page.error] };
  if (page.res.status !== 200) {
    await discard(page.res);
    return {
      error: page.res.status === 404
        ? 'That hopper was not found (404). Check the URL, and make sure the hopper is set to public in Studio.'
        : `That hopper page answered ${page.res.status}, so it is not a public hopper.`,
    };
  }
  const type = page.res.headers.get('content-type') || '';
  if (!/text\/html|application\/xhtml\+xml/i.test(type)) {
    await discard(page.res);
    return { error: 'That URL does not serve a web page, so it is not a hopper page.' };
  }
  const html = (await page.res.text()).slice(0, MAX_HTML_CHARS);
  const finalPage = normalizeLoose(page.url);

  // 3. The blyg manifest.
  const found = await resolveManifest(html, finalPage, slug, ctx);
  if (!found) {
    return { error: 'That page is not part of a blyg: no blyg manifest (blyg.json) was found for it.' };
  }
  const { manifest, manifestUrl } = found;
  if (!supportedBlygVersion(manifest.blyg)) {
    return { error: `That blyg speaks protocol version ${String(manifest.blyg).slice(0, 20)}; only 0.1–0.4 are supported.` };
  }

  // 4. Identity — never the manifest's self-asserted `site`.
  const base = identityOf(manifestUrl);

  // 5. The page must be exactly {identity}h/{slug}/.
  if (!finalPage.startsWith(base) || finalPage.slice(base.length) !== `h/${slug}/`) {
    return { error: `That page is not a hopper of the blyg at ${base} (expected ${base}h/${slug}/).` };
  }

  // 7. Manifest hoppers[] (future slot).
  const listed = matchManifestHoppers(manifest, base, finalPage);
  if (listed.error) return listed;

  // 6. Record.
  return {
    ok: true,
    canonical,
    base,
    slug,
    title: extractTitle(html),
    blyg_title: manifestTitle(manifest),
    generator: typeof manifest.generator === 'string' ? manifest.generator.slice(0, 200) : null,
    blyg_version: manifest.blyg.trim(),
    manifest_url: manifestUrl,
    final_url: finalPage,
    feed: listed.feed,
  };
}

function manifestTitle(manifest) {
  if (typeof manifest.title === 'string' && manifest.title.trim()) return manifest.title.trim().slice(0, 200);
  const site = manifest.site;
  if (site && typeof site === 'object' && typeof site.title === 'string') return site.title.trim().slice(0, 200);
  return null;
}

// ── HTML scraps (no DOM in Workers outside HTMLRewriter; keep it regex-small) ─

function parseAttrs(tag) {
  const attrs = {};
  const re = /([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  const body = tag.replace(/^<\w+/, '');
  let m;
  while ((m = re.exec(body))) {
    attrs[m[1].toLowerCase()] = m[2] ?? m[3] ?? m[4] ?? '';
  }
  return attrs;
}

/** href of the first <link rel="blyg" …> (rel is a token list). */
export function findRelBlygHref(html) {
  for (const tag of html.match(/<link\b[^>]*>/gi) || []) {
    const attrs = parseAttrs(tag);
    const rels = (attrs.rel || '').toLowerCase().split(/\s+/);
    if (rels.includes('blyg') && attrs.href) return decodeEntities(attrs.href.trim());
  }
  return null;
}

function extractTitle(html) {
  const m = html.match(/<title[^>]*>([\s\S]{1,400}?)<\/title>/i);
  if (!m) return null;
  const title = decodeEntities(m[1].replace(/\s+/g, ' ').trim()).slice(0, 200);
  return title || null;
}

function decodeEntities(s) {
  return s
    .replace(/&#(\d+);/g, (_, n) => safeCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => safeCodePoint(parseInt(n, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function safeCodePoint(n) {
  try { return String.fromCodePoint(n); } catch { return ''; }
}

// ── Storage ──────────────────────────────────────────────────────────────────

const withSlash = (s) => (s.endsWith('/') ? s : s + '/');
const withoutSlash = (s) => s.replace(/\/+$/, '');

export async function isBlocked(env, { base, email }) {
  const checks = [];
  if (base) checks.push(env.HOPPERS.get(BLOCK_BLYG + withSlash(base)), env.HOPPERS.get(BLOCK_BLYG + withoutSlash(base)));
  if (email) checks.push(env.HOPPERS.get(BLOCK_EMAIL + email));
  return (await Promise.all(checks)).some(Boolean);
}

/** The live (pending/approved) submission for a canonical URL, either spelling. */
export async function liveSubmissionFor(env, canonical) {
  const id = (await env.HOPPERS.get(CANON + withSlash(canonical))) || (await env.HOPPERS.get(CANON + withoutSlash(canonical)));
  return id ? getSubmission(env, id) : null;
}

export async function getSubmission(env, id) {
  const raw = await env.HOPPERS.get(SUB + id);
  return raw ? JSON.parse(raw) : null;
}

export async function saveSubmission(env, record) {
  await env.HOPPERS.put(SUB + record.id, JSON.stringify(record));
}

/** Validator fields copied onto a record. */
function validationFields(v) {
  return {
    url: v.canonical,
    canonical: v.canonical,
    base: v.base,
    slug: v.slug,
    title: v.title,
    blyg_title: v.blyg_title,
    generator: v.generator,
    blyg_version: v.blyg_version,
    manifest_url: v.manifest_url,
    feed: v.feed,
    validated_at: new Date().toISOString(),
    validation_error: null,
  };
}

/** Store a validated hopper as accepted. `fields` carries the submitter's details. */
export async function createSubmission(env, validation, fields) {
  const now = new Date().toISOString();
  const record = {
    id: crypto.randomUUID(),
    status: 'approved',
    submitted_at: now,
    decided_at: now,
    decided_by: AUTO_APPROVER,
    ...fields,
    ...validationFields(validation),
  };
  await saveSubmission(env, record);
  await env.HOPPERS.put(CANON + record.canonical, record.id);
  return record;
}

/**
 * Re-run the validator on an existing record. Passing refreshes its metadata
 * (moving its canon: key if the canonical spelling changed) and approves it if
 * it was pending; failing records the error and leaves the status alone.
 * @returns {Promise<{record:object}|{error:string, status:number, record?:object}>}
 */
export async function revalidate(env, record, opts) {
  const v = await validateHopper(record.canonical || record.url, opts);
  if (v.error) {
    record.validation_error = v.error;
    record.validated_at = new Date().toISOString();
    await saveSubmission(env, record);
    return { error: v.error, status: 422, record };
  }
  const holder = await liveSubmissionFor(env, v.canonical);
  if (holder && holder.id !== record.id) {
    return { error: 'Another submission already holds that hopper URL.', status: 409 };
  }
  if (await isBlocked(env, { base: v.base, email: record.email })) {
    return { error: 'That blyg or submitter is blocked.', status: 403 };
  }
  const oldCanonical = record.canonical;
  Object.assign(record, validationFields(v));
  if (record.status === 'pending') {
    record.status = 'approved';
    record.decided_at = new Date().toISOString();
    record.decided_by = AUTO_APPROVER;
  }
  await saveSubmission(env, record);
  if (oldCanonical && oldCanonical !== record.canonical) await env.HOPPERS.delete(CANON + oldCanonical);
  await env.HOPPERS.put(CANON + record.canonical, record.id);
  return { record };
}

/** Approve or reject. Rejection frees the URL's live slot and blocks the blyg + email. */
export async function decide(env, record, status, adminEmail) {
  record.status = status;
  record.decided_at = new Date().toISOString();
  record.decided_by = adminEmail;
  await saveSubmission(env, record);
  if (status === 'rejected') {
    await Promise.all([
      env.HOPPERS.delete(CANON + record.canonical),
      env.HOPPERS.put(BLOCK_BLYG + withSlash(record.base), record.id),
      record.email ? env.HOPPERS.put(BLOCK_EMAIL + record.email, record.id) : null,
    ]);
  }
  return record;
}

/**
 * The public face of an approved record (GET /api/hoppers). Another agent
 * consumes this shape — keep it stable. Never includes the email.
 */
export function publicHopper(s) {
  const canonical = withSlash(s.canonical || s.url);
  return {
    canonical,
    url: canonical,
    base: withSlash(s.base),
    slug: s.slug,
    title: s.title || null,
    blyg_title: s.blyg_title || null,
    feed: s.feed || null,
    name: s.name || null,
    handle: s.handle || null,
    submitted_at: s.submitted_at,
    approved_at: s.decided_at || null,
  };
}

export async function listSubmissions(env) {
  const keys = [];
  let cursor;
  do {
    const page = await env.HOPPERS.list({ prefix: SUB, cursor });
    keys.push(...page.keys);
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  const rows = await Promise.all(keys.map(({ name }) => env.HOPPERS.get(name)));
  return rows
    .filter(Boolean)
    .map((raw) => JSON.parse(raw))
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at));
}
