// Hopper submissions — the queue behind /hoppers and /admin/hoppers.
//
// Anyone can propose the URL of a public blyg hopper (`{mount}/h/{slug}`) for
// the World Machines blyg at blyg.worldmachines.org. Aneesh approves or rejects.
// Approval only records the hopper: stock blygger (v0.46) cannot subscribe to a
// hopper — it is an HTML page with no feed, and POST /api/subscriptions on its
// URL would resolve to the member's WHOLE blyg. Polling + filing waits for
// hopper feeds (blygger-spec Fable queue item 14).
//
// KV layout (binding HOPPERS — its own namespace, because HANDLES is listed
// whole by /api/contributors, /api/admin/handles and provision-access.mjs):
//
//   sub:<id>             submission record (see makeRecord)
//   canon:<canonical>    id of the live (pending/approved) submission for a URL
//   block:blyg:<base>    id of the rejection that blocked this blyg
//   block:email:<email>  id of the rejection that blocked this submitter
//
// A rejection blocks the submitter's email AND their whole blyg (origin + mount),
// not just the one hopper URL — otherwise "may not re-submit" is one new slug
// away. The email is self-reported (the form is public, like /join), so the
// blyg block is the one that actually holds.

export const SUB = 'sub:';
const CANON = 'canon:';
const BLOCK_BLYG = 'block:blyg:';
const BLOCK_EMAIL = 'block:email:';

const FETCH_TIMEOUT_MS = 8000;

/**
 * Parse a submitted hopper URL.
 * @returns {{canonical:string, base:string, slug:string}|{error:string}}
 */
export function parseHopperUrl(raw) {
  let url;
  try {
    url = new URL(String(raw || '').trim());
  } catch {
    return { error: 'That is not a valid URL.' };
  }
  if (url.protocol !== 'https:') return { error: 'Hopper URLs must be https.' };
  const path = url.pathname.replace(/\/+$/, '');
  const match = path.match(/^(.*)\/h\/([a-z0-9][a-z0-9-]{0,79})$/i);
  if (!match) {
    return { error: 'That does not look like a public hopper URL — it should end in /h/<hopper-name>.' };
  }
  const base = `${url.protocol}//${url.host.toLowerCase()}${match[1]}`;
  const slug = match[2].toLowerCase();
  return { canonical: `${base}/h/${slug}`, base, slug };
}

/** Fetch the hopper page; it must answer 200 with HTML. Returns the page title if any. */
export async function probeHopper(canonical) {
  let res;
  try {
    res = await fetch(canonical, {
      headers: { Accept: 'text/html', 'User-Agent': 'worldmachines-hoppers (+https://worldmachines.org/hoppers)' },
      redirect: 'follow',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch {
    return { error: 'Could not reach that hopper. Is the blyg online?' };
  }
  if (!res.ok) return { error: `That hopper page answered ${res.status}. Is it public?` };
  if (!(res.headers.get('content-type') || '').includes('text/html')) {
    return { error: 'That URL does not serve a web page.' };
  }
  const head = (await res.text()).slice(0, 20000);
  const title = head.match(/<title[^>]*>([^<]{1,200})<\/title>/i);
  return { title: title ? decodeEntities(title[1].trim()) : null };
}

function decodeEntities(s) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&#x27;/g, "'");
}

export async function isBlocked(env, { base, email }) {
  const [byBlyg, byEmail] = await Promise.all([
    env.HOPPERS.get(BLOCK_BLYG + base),
    email ? env.HOPPERS.get(BLOCK_EMAIL + email) : null,
  ]);
  return Boolean(byBlyg || byEmail);
}

export async function liveSubmissionFor(env, canonical) {
  const id = await env.HOPPERS.get(CANON + canonical);
  return id ? getSubmission(env, id) : null;
}

export async function getSubmission(env, id) {
  const raw = await env.HOPPERS.get(SUB + id);
  return raw ? JSON.parse(raw) : null;
}

export async function saveSubmission(env, record) {
  await env.HOPPERS.put(SUB + record.id, JSON.stringify(record));
}

export async function createSubmission(env, fields) {
  const record = {
    id: crypto.randomUUID(),
    status: 'pending',
    submitted_at: new Date().toISOString(),
    decided_at: null,
    decided_by: null,
    ...fields,
  };
  await saveSubmission(env, record);
  await env.HOPPERS.put(CANON + record.canonical, record.id);
  return record;
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
      env.HOPPERS.put(BLOCK_BLYG + record.base, record.id),
      record.email ? env.HOPPERS.put(BLOCK_EMAIL + record.email, record.id) : null,
    ]);
  }
  return record;
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
