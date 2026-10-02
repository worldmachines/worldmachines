// Fetch relay for the ingest bot (scripts/article_fetch.py).
//
// GitHub Actions runners sit on Azure IPs that Substack and many
// Cloudflare-protected blogs answer with a 403 challenge, while the same
// request from Cloudflare's network gets through. The ingest job therefore
// asks this function to make the request for it when a direct fetch fails.
//
//   GET /api/ingest-relay?url=<http(s) URL>   → upstream status + body
//   GET /api/ingest-relay?pasted=<key>        → text a member pasted on /submit
//                                               (stored in LIBRARY under _ingest/pasted/)
//
// Bearer INGEST_RELAY_TOKEN only — without it this would be an open proxy.
// Requests identify themselves honestly; nothing here pretends to be a browser.

const USER_AGENT = 'worldmachines-ingest/1.0 (+https://worldmachines.org)';
const MAX_BYTES = 8 * 1024 * 1024;
export const PASTED_PREFIX = '_ingest/pasted/';

function authorized(request, env) {
  const want = env.INGEST_RELAY_TOKEN || '';
  const got = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!want || got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= want.charCodeAt(i) ^ got.charCodeAt(i);
  return diff === 0;
}

async function fetchUpstream(target) {
  // One polite retry: Substack rate-limits Cloudflare's shared egress with 429s.
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch(target, {
      headers: { 'User-Agent': USER_AGENT, Accept: 'text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8' },
      redirect: 'follow',
    });
    if (res.status !== 429 || attempt === 1) return res;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

export async function onRequestGet({ request, env }) {
  if (!authorized(request, env)) return new Response('Not found', { status: 404 });

  const params = new URL(request.url).searchParams;

  const pasted = params.get('pasted');
  if (pasted) {
    if (!/^[\w-]{8,80}\.txt$/.test(pasted)) return new Response('Bad key', { status: 400 });
    const object = await env.LIBRARY.get(PASTED_PREFIX + pasted);
    if (!object) return new Response('Not found', { status: 404 });
    return new Response(object.body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }

  let target;
  try {
    target = new URL(params.get('url') || '');
  } catch {
    return new Response('Bad url', { status: 400 });
  }
  if (!['http:', 'https:'].includes(target.protocol)) return new Response('Bad url', { status: 400 });

  let upstream;
  try {
    upstream = await fetchUpstream(target.toString());
  } catch (err) {
    return new Response(`Upstream error: ${err}`, { status: 502 });
  }
  const body = await upstream.arrayBuffer();
  if (body.byteLength > MAX_BYTES) return new Response('Too large', { status: 413 });

  return new Response(body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'application/octet-stream',
      'X-Upstream-Url': upstream.url,
      'Cache-Control': 'no-store',
    },
  });
}
