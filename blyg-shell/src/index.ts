/**
 * wm-blyg-shell: the worldmachines.org site bar on blyg.worldmachines.org.
 *
 * The blyg is Blygger Studio, a separate Worker (blyg-blyg-worldmachines-org)
 * whose public pages offer no template hook. This Worker owns the custom
 * domain instead, hands every request to Studio unchanged through the STUDIO
 * service binding, and on public HTML pages only splices in the site bar:
 *
 *   <head>  + <link rel="stylesheet" href="{NAV_CSS_URL}">
 *   <body>  + the partial at NAV_PARTIAL_URL, before Studio's div.blyg
 *
 * Both files are built by website/scripts/build.py and deploy with the site.
 * Anything that goes wrong on the nav side serves Studio's page unmodified.
 */

export interface Env {
  STUDIO: Fetcher;
  /** The bar's markup. Empty string = kill switch: pass everything through. */
  NAV_PARTIAL_URL: string;
  NAV_CSS_URL: string;
  /** Edge cache for the partial, in seconds. */
  NAV_CACHE_TTL?: string;
}

/**
 * Path prefixes that are never public pages. From Studio's src/index.ts route
 * table and RESERVED_PATHS (src/front-page.ts), at MOUNT "":
 *   /studio (SPA, /studio/auth OAuth + its /.well-known, /studio/mcp), /api
 *   (owner + authorization APIs), /media (uploads, some owner-only), /items
 *   (JSON), /webmention (POST endpoint); plus names Studio reserves for
 *   itself (auth, mcp, feed, rss, atom) and /oauth, /.well-known for safety.
 * The rewrite also requires a 200 text/html answer, so a miss here can only
 * ever leave a page unmodified, never rewrite JSON or XML.
 */
export const EXCLUDED_PREFIXES = [
  '/studio', '/api', '/auth', '/oauth', '/mcp', '/.well-known',
  '/media', '/items', '/webmention', '/feed', '/rss', '/atom',
];
/** Exact non-HTML files on the public surface. */
export const EXCLUDED_FILES = ['/feed.xml', '/blyg.json', '/style.css', '/blogroll.opml'];

export function isPageCandidate(request: Request): boolean {
  if (request.method !== 'GET' && request.method !== 'HEAD') return false;
  const path = new URL(request.url).pathname;
  if (EXCLUDED_FILES.includes(path)) return false;
  return !EXCLUDED_PREFIXES.some(p => path === p || path.startsWith(p + '/'));
}

interface Nav {
  html: string;
  /** Short hash of the partial and the CSS URL: the nav's version. */
  version: string;
}

// Best-effort memo inside one isolate, on top of the edge cache, so a busy
// isolate does not even make the cached subrequest on every page view.
// A failure is remembered for less time, and spares every page view the wait
// for a site that is not answering.
const MEMO_MS = 60_000;
const FAIL_MEMO_MS = 15_000;
let memo: { url: string; at: number; nav: Nav | null } | null = null;

/** For tests: forget the in-isolate copy of the partial. */
export function resetNavMemo(): void {
  memo = null;
}

async function shortHash(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest).slice(0, 6), b => b.toString(16).padStart(2, '0')).join('');
}

export async function loadNav(env: Env): Promise<Nav | null> {
  const url = env.NAV_PARTIAL_URL;
  if (!url) return null;
  const now = Date.now();
  if (memo && memo.url === url && now - memo.at < (memo.nav ? MEMO_MS : FAIL_MEMO_MS)) return memo.nav;
  const nav = await fetchNav(env, url);
  memo = { url, at: now, nav };
  return nav;
}

async function fetchNav(env: Env, url: string): Promise<Nav | null> {
  const ttl = Number(env.NAV_CACHE_TTL ?? '300') || 300;
  try {
    const res = await fetch(url, {
      cf: { cacheTtl: ttl, cacheEverything: true },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    const html = await res.text();
    // Pages answers a missing file with the site's index.html (200, and it
    // too holds a sitenav), so only the partial's own root is accepted.
    if (!html.trimStart().startsWith('<div class="wm-sitechrome">')) return null;
    return { html, version: await shortHash(html + '\n' + env.NAV_CSS_URL) };
  } catch {
    return null;
  }
}

/** Mark the pinned-row link for the page being viewed with aria-current. */
export function markCurrent(html: string, pathname: string): string {
  const norm = (p: string) => p.replace(/\/+$/, '') || '/';
  const here = norm(pathname);
  return html.replace(/<div class="nav-pinned">[\s\S]*?<\/div>/, row => {
    let blygHost: string | null = null;
    return row.replace(/<a href="([^"]+)">/g, (tag, href: string) => {
      let u: URL;
      try { u = new URL(href); } catch { return tag; }
      // The row's first link is the blyg's front page; its host is the blyg's.
      blygHost ??= u.host;
      return u.host === blygHost && norm(u.pathname) === here ? `<a href="${href}" aria-current="page">` : tag;
    });
  });
}

/** Studio's validator with the nav's version folded in. */
export function navEtag(etag: string | null, version: string): string | null {
  if (!etag) return null;
  const m = /^(W\/)?"(.*)"$/.exec(etag.trim());
  return m ? `W/"${m[2]}-nav${version}"` : null;
}

function etagMatches(header: string | null, etag: string): boolean {
  if (!header) return false;
  const bare = etag.replace(/^W\//, '');
  return header.split(',').some(t => t.trim() === '*' || t.trim().replace(/^W\//, '') === bare);
}

function isHtml(response: Response): boolean {
  return response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() === 'text/html';
}

export async function handle(request: Request, env: Env): Promise<Response> {
  if (!isPageCandidate(request) || !env.NAV_PARTIAL_URL) return env.STUDIO.fetch(request);

  // Validators the browser holds may predate the nav (Studio's bare tag) or
  // carry another nav version. Studio would answer a bare match with a 304
  // and hide a nav change, so it never sees them: this Worker validates.
  const forwarded = new Request(request);
  forwarded.headers.delete('if-none-match');
  forwarded.headers.delete('if-modified-since');

  const [response, nav] = await Promise.all([env.STUDIO.fetch(forwarded), loadNav(env)]);
  if (response.status !== 200 || !isHtml(response) || !nav) return response;

  const headers = new Headers(response.headers);
  headers.delete('content-length');
  headers.set('X-WM-Nav', nav.version);
  const etag = navEtag(response.headers.get('etag'), nav.version);
  if (etag) headers.set('ETag', etag);
  else headers.delete('ETag');

  if (etag && etagMatches(request.headers.get('if-none-match'), etag)) {
    return new Response(null, { status: 304, headers });
  }
  if (request.method === 'HEAD' || response.body === null) {
    return new Response(null, { status: 200, statusText: response.statusText, headers });
  }

  const bar = markCurrent(nav.html, new URL(request.url).pathname);
  const css = `<link rel="stylesheet" href="${env.NAV_CSS_URL}">`;
  const rewritten = new HTMLRewriter()
    .on('head', { element(el) { el.append(css, { html: true }); } })
    .on('body', { element(el) { el.prepend(bar, { html: true }); } })
    .transform(new Response(response.body, { status: 200, statusText: response.statusText, headers }));
  return rewritten;
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handle(request, env);
  },
} satisfies ExportedHandler<Env>;
