import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { handle, isPageCandidate, markCurrent, navEtag, resetNavMemo, type Env } from '../src/index.ts';

const BLYG = 'https://blyg.worldmachines.org';
const PARTIAL_URL = 'https://worldmachines.org/partials/sitenav-blyg.html';
const CSS_URL = 'https://worldmachines.org/nav.css';

const partial = (marker = 'v1') => `<div class="wm-sitechrome">
  <nav class="sitenav" aria-label="Main"><!-- ${marker} -->
    <ul class="nav-bar">
      <li class="nav-item is-current"><a class="nav-label" href="${BLYG}/">Blyg</a></li>
    </ul>
    <div class="nav-pinned">
      <a href="${BLYG}/">Front page</a>
      <a href="${BLYG}/posts/">All posts</a>
      <a href="https://worldmachines.org/hoppers">Submit a hopper</a>
    </div>
  </nav>
</div>
`;

const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>worldmachines.org</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="blyg has-side side-left">
<p>Hello</p>
</div>
</body>
</html>
`;

const HTML_HEADERS = {
  'Content-Type': 'text/html; charset=UTF-8',
  'Content-Length': String(PAGE.length),
  ETag: 'W/"abc123"',
  'Cache-Control': 'no-cache',
  'Cloudflare-CDN-Cache-Control': 'public, max-age=60, stale-while-revalidate=300, stale-if-error=0',
  Link: `<${BLYG}/webmention>; rel="webmention"`,
};

/** A stand-in for Studio that answers by path and records what it was sent. */
function studio() {
  const seen: Request[] = [];
  const fetcher = {
    async fetch(input: RequestInfo, init?: RequestInit) {
      const req = new Request(input, init);
      seen.push(req);
      const path = new URL(req.url).pathname;
      if (path === '/feed.xml') {
        return new Response('<?xml version="1.0"?><rss></rss>', { headers: { 'Content-Type': 'application/rss+xml' } });
      }
      if (path === '/blyg.json') return Response.json({ title: 'x' });
      if (path.startsWith('/studio') || path.startsWith('/api')) {
        // HTML too, to prove exclusion is by path and not only by type.
        return new Response(PAGE, { headers: { 'Content-Type': 'text/html', 'Set-Cookie': 'sid=1; HttpOnly' } });
      }
      if (path === '/missing') return new Response('<html><body>nope</body></html>', { status: 404, headers: { 'Content-Type': 'text/html' } });
      if (req.method === 'HEAD') return new Response(null, { headers: HTML_HEADERS });
      return new Response(PAGE, { headers: HTML_HEADERS });
    },
    connect() { throw new Error('unused'); },
  };
  return { fetcher: fetcher as unknown as Fetcher, seen };
}

let navBody: string | null;
let navFetches: number;

function env(overrides: Partial<Env> = {}): { env: Env; seen: Request[] } {
  const s = studio();
  return { env: { STUDIO: s.fetcher, NAV_PARTIAL_URL: PARTIAL_URL, NAV_CSS_URL: CSS_URL, NAV_CACHE_TTL: '300', ...overrides }, seen: s.seen };
}

beforeEach(() => {
  resetNavMemo();
  navBody = partial();
  navFetches = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url !== PARTIAL_URL) return new Response('unexpected', { status: 500 });
    navFetches++;
    if (navBody === null) throw new TypeError('network down');
    return new Response(navBody, { headers: { 'Content-Type': 'text/html' } });
  });
});
afterEach(() => vi.restoreAllMocks());

const get = (path: string, init?: RequestInit) => new Request(BLYG + path, init);

describe('public HTML pages', () => {
  it('gets the stylesheet in <head> and the bar first in <body>', async () => {
    const { env: e } = env();
    const res = await handle(get('/'), e);
    const html = await res.text();
    expect(res.status).toBe(200);
    expect(html).toContain(`<link rel="stylesheet" href="/style.css">\n<link rel="stylesheet" href="${CSS_URL}"></head>`);
    expect(html).toMatch(/<body>\s*<div class="wm-sitechrome">[\s\S]*<\/div>\s*\n<div class="blyg has-side side-left">/);
    expect(html.match(/wm-sitechrome/g)?.length).toBe(1);
  });

  it('works on thread permalinks and the posts page', async () => {
    for (const path of ['/t/2a57d11z0jkteq92da2p7qw1m2', '/posts/', '/archive', '/h/members/']) {
      const html = await (await handle(get(path), env().env)).text();
      expect(html, path).toContain('class="wm-sitechrome"');
    }
  });

  it('marks the pinned link for the current page', async () => {
    const html = await (await handle(get('/posts/'), env().env)).text();
    expect(html).toContain(`<a href="${BLYG}/posts/" aria-current="page">All posts</a>`);
    expect(html).toContain(`<a href="${BLYG}/">Front page</a>`);
  });

  it('drops Content-Length and keeps Studio caching headers', async () => {
    const res = await handle(get('/'), env().env);
    expect(res.headers.get('content-length')).toBeNull();
    expect(res.headers.get('cache-control')).toBe('no-cache');
    expect(res.headers.get('cloudflare-cdn-cache-control')).toBe(HTML_HEADERS['Cloudflare-CDN-Cache-Control']);
    expect(res.headers.get('link')).toBe(HTML_HEADERS.Link);
  });

  it('folds the nav version into the ETag, so a nav change moves it', async () => {
    const a = await handle(get('/'), env().env);
    const tagA = a.headers.get('etag')!;
    expect(tagA).toMatch(/^W\/"abc123-nav[0-9a-f]{12}"$/);
    resetNavMemo();
    navBody = partial('v2');
    const b = await handle(get('/'), env().env);
    expect(b.headers.get('etag')).not.toBe(tagA);
    expect(b.headers.get('etag')).toMatch(/^W\/"abc123-nav/);
  });

  it('answers 304 itself for a matching tag, and never lets Studio validate', async () => {
    const tag = (await handle(get('/'), env().env)).headers.get('etag')!;
    const { env: e, seen } = env();
    const res = await handle(get('/', { headers: { 'If-None-Match': tag } }), e);
    expect(res.status).toBe(304);
    expect(await res.text()).toBe('');
    expect(seen[0].headers.get('if-none-match')).toBeNull();
  });

  it("a pre-nav browser tag (Studio's bare one) gets the full page", async () => {
    const { env: e, seen } = env();
    const res = await handle(get('/', { headers: { 'If-None-Match': 'W/"abc123"' } }), e);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('wm-sitechrome');
    expect(seen[0].headers.get('if-none-match')).toBeNull();
  });

  it('HEAD: no body, nav ETag, no Content-Length', async () => {
    const getTag = (await handle(get('/'), env().env)).headers.get('etag');
    const res = await handle(get('/', { method: 'HEAD' }), env().env);
    expect(res.status).toBe(200);
    expect(res.body).toBeNull();
    expect(res.headers.get('etag')).toBe(getTag);
    expect(res.headers.get('content-length')).toBeNull();
  });

  it('fetches the partial once per isolate window', async () => {
    const { env: e } = env();
    await handle(get('/'), e);
    await handle(get('/posts/'), e);
    expect(navFetches).toBe(1);
  });
});

describe('fallbacks: the page is served unmodified', () => {
  it('when the partial cannot be fetched', async () => {
    navBody = null;
    const res = await handle(get('/'), env().env);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe(PAGE);
    expect(res.headers.get('etag')).toBe('W/"abc123"');
  });

  it("when the site answers with something that isn't the partial (Pages' index fallback)", async () => {
    navBody = '<!DOCTYPE html><html><body><nav class="sitenav"></nav></body></html>';
    const res = await handle(get('/'), env().env);
    expect(await res.text()).toBe(PAGE);
  });

  it('when the kill switch is on (NAV_PARTIAL_URL empty)', async () => {
    const { env: e, seen } = env({ NAV_PARTIAL_URL: '' });
    const res = await handle(get('/', { headers: { 'If-None-Match': 'W/"abc123"' } }), e);
    expect(await res.text()).toBe(PAGE);
    expect(navFetches).toBe(0);
    // Untouched: the browser's validator reaches Studio as sent.
    expect(seen[0].headers.get('if-none-match')).toBe('W/"abc123"');
  });

  it('for a 404 page', async () => {
    const res = await handle(get('/missing'), env().env);
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain('wm-sitechrome');
  });
});

describe('pass-through', () => {
  it('/studio and /api come back byte-identical, request unchanged', async () => {
    for (const path of ['/studio', '/studio/items/x', '/api/items', '/studio/auth/.well-known/openid-configuration']) {
      const { env: e, seen } = env();
      const req = get(path, { headers: { Cookie: 'sid=1', 'If-None-Match': 'W/"x"' } });
      const res = await handle(req, e);
      expect(await res.text(), path).toBe(PAGE);
      expect(res.headers.get('set-cookie')).toBe('sid=1; HttpOnly');
      expect(seen[0].headers.get('cookie')).toBe('sid=1');
      expect(seen[0].headers.get('if-none-match')).toBe('W/"x"');
      expect(seen[0].url).toBe(BLYG + path);
    }
    expect(navFetches).toBe(0);
  });

  it('feed.xml and JSON are untouched', async () => {
    const feed = await handle(get('/feed.xml'), env().env);
    expect(await feed.text()).toBe('<?xml version="1.0"?><rss></rss>');
    expect(feed.headers.get('content-type')).toBe('application/rss+xml');
    const json = await handle(get('/blyg.json'), env().env);
    expect(await json.json()).toEqual({ title: 'x' });
    expect(navFetches).toBe(0);
  });

  it('POST goes straight through with its body', async () => {
    const { env: e, seen } = env();
    await handle(get('/webmention', { method: 'POST', body: 'source=a&target=b', headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }), e);
    expect(seen[0].method).toBe('POST');
    expect(await seen[0].text()).toBe('source=a&target=b');
  });
});

describe('helpers', () => {
  it('isPageCandidate', () => {
    expect(isPageCandidate(get('/'))).toBe(true);
    expect(isPageCandidate(get('/t/abc'))).toBe(true);
    expect(isPageCandidate(get('/posts/'))).toBe(true);
    expect(isPageCandidate(get('/studio'))).toBe(false);
    expect(isPageCandidate(get('/studio/'))).toBe(false);
    expect(isPageCandidate(get('/studioish'))).toBe(true);
    expect(isPageCandidate(get('/media/x.png'))).toBe(false);
    expect(isPageCandidate(get('/.well-known/x'))).toBe(false);
    expect(isPageCandidate(get('/style.css'))).toBe(false);
    expect(isPageCandidate(get('/', { method: 'POST' }))).toBe(false);
  });

  it('navEtag', () => {
    expect(navEtag('W/"abc"', 'f00')).toBe('W/"abc-navf00"');
    expect(navEtag('"abc"', 'f00')).toBe('W/"abc-navf00"');
    expect(navEtag(null, 'f00')).toBeNull();
  });

  it('markCurrent only touches the pinned row', () => {
    const out = markCurrent(partial(), '/');
    expect(out).toContain(`<a href="${BLYG}/" aria-current="page">Front page</a>`);
    expect(out).toContain(`<a class="nav-label" href="${BLYG}/">Blyg</a>`);
    expect(markCurrent(partial(), '/hoppers')).not.toContain('aria-current');
  });
});
