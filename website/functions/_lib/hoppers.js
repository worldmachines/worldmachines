// Hopper submissions — the list behind /hoppers and /admin/hoppers.
//
// Anyone can propose the URL of a public blyg hopper for the World Machines
// blyg at blyg.worldmachines.org. On Blygger Studio that is `{mount}h/{slug}/`;
// on a blyg whose manifest lists its hoppers (spec 0.4 §6.1), any page it
// names. A submission that validates as a real public blyg hopper
// (validateHopper below) is accepted at once (status `approved`); anything
// else is refused with a reason. The admin can still reject (and so block) an
// accepted hopper later. A record left `pending` by the old approve-first flow
// is re-validated when its hopper is submitted again (/api/hoppers POST), or
// from /admin/hoppers.
//
// Accepting records the hopper and fires the blyg sync (.github/workflows/
// blyg-sync.yml), which follows the hopper itself through its hopper feed when
// the member's blyg offers one (Studio ≥ 0.50 with hopper feeds on; `feed`
// below), and otherwise reads the hopper page.
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
// Spec 0.4 §6.1 (decision #86): a blyg MAY list its public hoppers in its
// manifest as `hoppers: [{title, page, feed?}]`, `page`/`feed` relative to the
// identity origin or absolute. Paths are presentation — `h/{slug}/` is only
// Blygger Studio's convention — so when the manifest lists hoppers, that list
// is the authority and the path shape is not checked. Without the key (blygs
// that predate it, or Studio with hopper feeds off) the convention is the best
// check available (algorithm from the blygger-spec maintainers; modelled on
// blygger-studio src/importer/resolve.ts, not vendored):
//   1. normalize the URL (https, no query/fragment, trailing "/" on a directory)
//   2. the page answers 200 HTML (Studio 404s private/unknown hoppers)
//   3. resolve the blyg manifest: rel="blyg" link → h/ mount → each ancestor
//      directory of the page → /blyg/ → /
//   4. identity origin = manifest's final URL minus its last segment
//   5. manifest lists hoppers[] → the page must be one of them (§12.1 step 7);
//      otherwise the final page URL is exactly {identity}h/{slug}/ (catches soft-404s)

/** Strip query + fragment; a directory-like path (last segment has no ".") ends in "/". */
function normalizeLoose(raw) {
  const u = new URL(raw);
  u.search = '';
  u.hash = '';
  const last = u.pathname.slice(u.pathname.lastIndexOf('/') + 1);
  if (!u.pathname.endsWith('/') && !last.includes('.')) u.pathname += '/';
  return u.toString();
}

const CONVENTION_ERROR =
  'That does not look like a public hopper URL. It should end in /h/<hopper-name>/, ' +
  'where the name is lowercase letters, digits and hyphens.';

/**
 * Step 1. Normalize a submitted hopper URL. Any https URL is accepted here;
 * `conventional` says whether it has Studio's `…/h/{slug}/` shape, which only
 * matters for a blyg whose manifest does not list its hoppers.
 * @returns {{canonical:string, slug:string|null, mount:string, conventional:boolean}|{error:string}}
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
  if (match && SLUG_RE.test(match[2])) {
    return { canonical, slug: match[2], mount: origin + match[1], conventional: true };
  }
  return { canonical, slug: lastSegment(pathname), mount: origin + '/', conventional: false };
}

/** The last non-empty path segment (decoded), or null at the root. */
function lastSegment(pathname) {
  const seg = pathname.split('/').filter(Boolean).pop();
  if (!seg) return null;
  try { return decodeURIComponent(seg).slice(0, 80); } catch { return seg.slice(0, 80); }
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
  if (slug && pageUrl.endsWith('/' + suffix)) {
    const found = await tryBase(pageUrl.slice(0, -suffix.length));
    if (found) return found;
  }

  // c. Each ancestor directory of the page, nearest first (a hopper at any
  //    path under its blyg), then the conventional /blyg/ mount.
  for (const base of ancestorDirs(pageUrl)) {
    const found = await tryBase(base);
    if (found) return found;
  }
  const found = await tryBase(`${new URL(pageUrl).origin}/blyg/`);
  if (found) return found;
  return null;
}

/** Directories above `pageUrl`, nearest first, ending at the host root; at most 6. */
function ancestorDirs(pageUrl) {
  const u = new URL(pageUrl);
  const parts = u.pathname.split('/').filter(Boolean);
  if (!u.pathname.endsWith('/')) parts.pop(); // a file-like page: start from its directory
  else parts.pop();                           // a directory page: start from its parent
  const dirs = [];
  for (let n = parts.length; n >= 0; n--) dirs.push(`${u.origin}/${parts.slice(0, n).map((p) => p + '/').join('')}`);
  return dirs.length > 6 ? [...dirs.slice(0, 5), dirs[dirs.length - 1]] : dirs;
}

/** Accept blyg protocol 0.1–0.4 (patch suffixes allowed). */
export function supportedBlygVersion(v) {
  return typeof v === 'string' && /^0\.[1-4](\.\d+)?$/.test(v.trim());
}

/**
 * Step 5a — spec 0.4 §6.1 `hoppers`: OPTIONAL array of the blyg's public
 * hoppers, each `{ title (REQUIRED), page (REQUIRED), feed (OPTIONAL) }`, with
 * `page`/`feed` relative to the identity origin or absolute, and no path
 * convention. Unknown members are ignored. If the manifest has the key, the
 * hopper page must be one of its entries (§12.1 step 7) and that entry's title
 * and feed are kept. Without the key there is nothing to check here.
 * @returns {{listed:boolean, feed:string|null, title?:string|null}|{error:string}}
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
    const title = typeof entry.title === 'string' && entry.title.trim() ? entry.title.trim().slice(0, 200) : null;
    return { listed: true, feed, title };
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
  const { canonical } = norm;
  let { slug } = norm;
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

  // 5a. A manifest that lists its hoppers is the authority: any path it names.
  const listed = matchManifestHoppers(manifest, base, finalPage);
  if (listed.error) return listed;

  // 5b. No list: fall back to Studio's convention, exactly {identity}h/{slug}/.
  if (!listed.listed) {
    if (!norm.conventional) return { error: CONVENTION_ERROR };
    if (!finalPage.startsWith(base) || finalPage.slice(base.length) !== `h/${slug}/`) {
      return { error: `That page is not a hopper of the blyg at ${base} (expected ${base}h/${slug}/).` };
    }
  } else {
    const conv = finalPage.startsWith(base) && finalPage.slice(base.length).match(/^h\/([^/]+)\/$/);
    slug = conv ? conv[1] : lastSegment(new URL(finalPage).pathname);
  }

  // 6. Record.
  return {
    ok: true,
    canonical,
    base,
    slug,
    title: extractTitle(html) || listed.title || null,
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
