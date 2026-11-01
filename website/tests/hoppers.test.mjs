// Validator tests for functions/_lib/hoppers.js with a mocked fetch.
// Run: node --test website/tests/

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeHopperUrl,
  validateHopper,
  matchManifestHoppers,
  findRelBlygHref,
  publicHopper,
  revalidate,
  liveSubmissionFor,
  isBlocked,
  decide,
} from '../functions/_lib/hoppers.js';

const MANIFEST = {
  blyg: '0.4',
  level: 2,
  generator: 'blygger-studio/0.49.1',
  site: 'https://venkateshrao.com/blyg/',
  title: "Venkatesh Rao's Blyg",
};

const html = (title, head = '') =>
  `<!doctype html><html><head><title>${title}</title>${head}</head><body>hopper</body></html>`;

/**
 * Routes: url → { status?, type?, body?, location? }. Unknown URLs 404.
 * Returns the fetch mock plus the list of URLs it was asked for.
 */
function mockFetch(routes) {
  const calls = [];
  const fetchFn = async (url, init) => {
    calls.push(url);
    assert.equal(init.redirect, 'manual', 'validator must follow redirects by hand');
    assert.ok(init.signal, 'every fetch needs a timeout signal');
    const r = routes[url];
    if (!r) return new Response('not found', { status: 404, headers: { 'content-type': 'text/html' } });
    if (r.throws) throw new TypeError('fetch failed');
    const headers = {};
    if (r.type) headers['content-type'] = r.type;
    if (r.location) headers.location = r.location;
    const body = typeof r.body === 'string' ? r.body : r.body ? JSON.stringify(r.body) : null;
    return new Response(r.status === 301 || r.status === 302 ? null : body, { status: r.status || 200, headers });
  };
  return { fetchFn, calls };
}

const page = (title, head) => ({ type: 'text/html; charset=UTF-8', body: html(title, head) });
const json = (body, type = 'application/json') => ({ type, body });

test('normalize: https only, strips query/fragment, adds trailing slash', () => {
  assert.deepEqual(normalizeHopperUrl('https://Example.com/blyg/h/history?x=1#y'), {
    canonical: 'https://example.com/blyg/h/history/',
    slug: 'history',
    mount: 'https://example.com/blyg/',
  });
  assert.match(normalizeHopperUrl('http://example.com/blyg/h/history/').error, /https/);
  assert.match(normalizeHopperUrl('https://example.com/blyg/history/').error, /\/h\//);
  assert.match(normalizeHopperUrl('https://example.com/h/Bad_Slug/').error, /lowercase/);
  assert.match(normalizeHopperUrl('not a url').error, /valid URL/);
});

test('rejects http before fetching anything', async () => {
  const { fetchFn, calls } = mockFetch({});
  const v = await validateHopper('http://venkateshrao.com/blyg/h/history/', { fetchFn });
  assert.match(v.error, /https/);
  assert.equal(calls.length, 0);
});

test('Venkat shape: hopper under /blyg/ mount, manifest at mount', async () => {
  const { fetchFn, calls } = mockFetch({
    'https://venkateshrao.com/blyg/h/history/': page('History — Venkatesh Rao&#39;s Blyg'),
    'https://venkateshrao.com/blyg/blyg.json': json(MANIFEST, 'text/plain'), // Content-Type not trusted
  });
  const v = await validateHopper('https://venkateshrao.com/blyg/h/history', { fetchFn });
  assert.equal(v.ok, true, v.error);
  assert.equal(v.canonical, 'https://venkateshrao.com/blyg/h/history/');
  assert.equal(v.base, 'https://venkateshrao.com/blyg/');
  assert.equal(v.slug, 'history');
  assert.equal(v.title, "History — Venkatesh Rao's Blyg");
  assert.equal(v.blyg_title, "Venkatesh Rao's Blyg");
  assert.equal(v.generator, 'blygger-studio/0.49.1');
  assert.equal(v.blyg_version, '0.4');
  assert.equal(v.feed, null);
  assert.deepEqual(calls, ['https://venkateshrao.com/blyg/h/history/', 'https://venkateshrao.com/blyg/blyg.json']);
});

test('404 hopper (private or unknown) is rejected', async () => {
  const { fetchFn } = mockFetch({
    'https://venkateshrao.com/blyg/blyg.json': json(MANIFEST),
  });
  const v = await validateHopper('https://venkateshrao.com/blyg/h/no-such-hopper-xyz/', { fetchFn });
  assert.match(v.error, /404/);
});

test('non-HTML page is rejected', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/h/x/': json({ hello: 1 }),
  });
  assert.match((await validateHopper('https://example.com/h/x/', { fetchFn })).error, /web page/);
});

test('soft-404: catch-all redirect lands outside h/{slug}/ → path mismatch', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/blyg/h/ghost/': { status: 302, location: '/blyg/' },
    'https://example.com/blyg/': page('Home'),
    'https://example.com/blyg/blyg.json': json(MANIFEST),
  });
  const v = await validateHopper('https://example.com/blyg/h/ghost/', { fetchFn });
  assert.match(v.error, /not a hopper of the blyg at https:\/\/example\.com\/blyg\//);
});

test('soft-404: page served 200 but the manifest lives on a deeper mount', async () => {
  // Host-wide catch-all answers 200 for /h/anything/, but the blyg is mounted at /blyg/.
  const { fetchFn } = mockFetch({
    'https://example.com/h/ghost/': page('Whatever'),
    'https://example.com/blyg/blyg.json': json(MANIFEST),
  });
  const v = await validateHopper('https://example.com/h/ghost/', { fetchFn });
  assert.match(v.error, /not a hopper of the blyg at https:\/\/example\.com\/blyg\//);
});

test('cross-host redirect: manifest resolves on the final host', async () => {
  const { fetchFn, calls } = mockFetch({
    'https://old.example/blyg/h/reading/': { status: 301, location: 'https://new.example/blyg/h/reading/' },
    'https://new.example/blyg/h/reading/': page('Reading'),
    'https://new.example/blyg/blyg.json': json({ ...MANIFEST, site: 'https://old.example/blyg/' }),
  });
  const v = await validateHopper('https://old.example/blyg/h/reading/', { fetchFn });
  assert.equal(v.ok, true, v.error);
  assert.equal(v.canonical, 'https://old.example/blyg/h/reading/', 'canonical stays the submitted URL');
  assert.equal(v.base, 'https://new.example/blyg/', 'identity comes from the manifest fetch, not `site`');
  assert.ok(!calls.includes('https://old.example/blyg/blyg.json'));
});

test('manifest redirect: identity is the manifest\'s FINAL URL minus its last segment', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/h/x/': page('X', '<link rel="blyg" href="/.well-known/blyg">'),
    'https://example.com/.well-known/blyg': { status: 302, location: 'https://example.com/manifest.json' },
    'https://example.com/manifest.json': json(MANIFEST),
  });
  const v = await validateHopper('https://example.com/h/x/', { fetchFn });
  assert.equal(v.ok, true, v.error);
  assert.equal(v.base, 'https://example.com/');
  assert.equal(v.manifest_url, 'https://example.com/manifest.json');
});

test('rel="blyg" href used as a base when it is not itself a manifest', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/site/h/x/': page('X', "<link href='/site/' rel='alternate blyg'>"),
    'https://example.com/site/': page('Site home'),
    'https://example.com/site/blyg.json': json(MANIFEST),
  });
  const v = await validateHopper('https://example.com/site/h/x/', { fetchFn });
  assert.equal(v.ok, true, v.error);
  assert.equal(v.base, 'https://example.com/site/');
});

test('manifest not found anywhere → rejected', async () => {
  const { fetchFn, calls } = mockFetch({
    'https://example.com/notes/h/x/': page('X'),
    'https://example.com/notes/blyg.json': json({ not: 'a manifest' }),
    'https://example.com/blyg.json': { type: 'text/html', body: '<html>soft 200</html>' },
  });
  const v = await validateHopper('https://example.com/notes/h/x/', { fetchFn });
  assert.match(v.error, /no blyg manifest/);
  assert.deepEqual(calls.slice(1), [
    'https://example.com/notes/blyg.json',
    'https://example.com/blyg/blyg.json',
    'https://example.com/blyg.json',
  ]);
});

test('unsupported blyg version → rejected', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/h/x/': page('X'),
    'https://example.com/blyg.json': json({ ...MANIFEST, blyg: '1.0' }),
  });
  assert.match((await validateHopper('https://example.com/h/x/', { fetchFn })).error, /0\.1–0\.4/);
});

test('redirect loop / too many hops → rejected', async () => {
  const routes = {};
  for (let i = 0; i < 7; i++) routes[`https://example.com/h/x${i}/`] = { status: 302, location: `/h/x${i + 1}/` };
  const { fetchFn } = mockFetch(routes);
  assert.match((await validateHopper('https://example.com/h/x0/', { fetchFn })).error, /redirects more than 5/);
});

test('redirect to http → rejected', async () => {
  const { fetchFn } = mockFetch({
    'https://example.com/h/x/': { status: 301, location: 'http://example.com/h/x/' },
  });
  assert.match((await validateHopper('https://example.com/h/x/', { fetchFn })).error, /non-https/);
});

test('unreachable host → rejected', async () => {
  const { fetchFn } = mockFetch({ 'https://example.com/h/x/': { throws: true } });
  assert.match((await validateHopper('https://example.com/h/x/', { fetchFn })).error, /Could not reach/);
});

test('hoppers[] slot: listed hopper passes and keeps its feed', async () => {
  const manifest = {
    ...MANIFEST,
    hoppers: [
      { title: 'Other', page: 'h/other/', feed: 'h/other/feed.xml' },
      { title: 'History', page: 'h/history/', feed: 'h/history/feed.xml' },
    ],
  };
  const { fetchFn } = mockFetch({
    'https://venkateshrao.com/blyg/h/history/': page('History'),
    'https://venkateshrao.com/blyg/blyg.json': json(manifest),
  });
  const v = await validateHopper('https://venkateshrao.com/blyg/h/history/', { fetchFn });
  assert.equal(v.ok, true, v.error);
  assert.equal(v.feed, 'https://venkateshrao.com/blyg/h/history/feed.xml');
});

test('hoppers[] slot: hopper missing from the list is rejected', async () => {
  const { fetchFn } = mockFetch({
    'https://venkateshrao.com/blyg/h/history/': page('History'),
    'https://venkateshrao.com/blyg/blyg.json': json({ ...MANIFEST, hoppers: [{ page: 'h/other/' }] }),
  });
  const v = await validateHopper('https://venkateshrao.com/blyg/h/history/', { fetchFn });
  assert.match(v.error, /not one of them/);
});

test('matchManifestHoppers: no key → nothing to check', () => {
  assert.deepEqual(matchManifestHoppers(MANIFEST, 'https://a.example/', 'https://a.example/h/x/'), { listed: false, feed: null });
  assert.deepEqual(
    matchManifestHoppers({ hoppers: [{ page: 'h/x' }] }, 'https://a.example/', 'https://a.example/h/x/'),
    { listed: true, feed: null }
  );
});

test('findRelBlygHref: rel token list, either quote style, entities', () => {
  assert.equal(findRelBlygHref('<link rel="stylesheet" href="/s.css"><link rel="blyg" href="/blyg/">'), '/blyg/');
  assert.equal(findRelBlygHref("<LINK REL='me blyg' HREF='/a?b=1&amp;c=2'>"), '/a?b=1&c=2');
  assert.equal(findRelBlygHref('<link rel="alternate" href="/feed.xml">'), null);
});

// ── Storage helpers against an in-memory KV ─────────────────────────────────

function memoryEnv() {
  const store = new Map();
  return {
    store,
    HOPPERS: {
      get: async (k) => store.get(k) ?? null,
      put: async (k, v) => void store.set(k, v),
      delete: async (k) => void store.delete(k),
      list: async ({ prefix }) => ({ keys: [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true }),
    },
  };
}

// A record as PR #100 wrote it: no trailing slashes, still pending.
const legacy = () => ({
  id: 'old-1',
  status: 'pending',
  submitted_at: '2026-10-01T00:00:00Z',
  decided_at: null,
  decided_by: null,
  url: 'https://venkateshrao.com/blyg/h/history',
  canonical: 'https://venkateshrao.com/blyg/h/history',
  base: 'https://venkateshrao.com/blyg',
  slug: 'history',
  title: 'History',
  name: 'Venkat',
  email: 'v@example.com',
  handle: 'vgr',
});

test('publicHopper normalizes legacy records and never leaks email', () => {
  const p = publicHopper({ ...legacy(), status: 'approved', decided_at: '2026-10-02T00:00:00Z' });
  assert.equal(p.canonical, 'https://venkateshrao.com/blyg/h/history/');
  assert.equal(p.base, 'https://venkateshrao.com/blyg/');
  assert.equal(p.slug, 'history');
  assert.equal(p.name, 'Venkat');
  assert.equal(p.submitted_at, '2026-10-01T00:00:00Z');
  assert.ok(!('email' in p));
});

test('revalidate: a legacy pending record passes → approved, canon key moved', async () => {
  const env = memoryEnv();
  const rec = legacy();
  env.store.set('sub:old-1', JSON.stringify(rec));
  env.store.set('canon:https://venkateshrao.com/blyg/h/history', 'old-1');
  assert.equal((await liveSubmissionFor(env, 'https://venkateshrao.com/blyg/h/history/')).id, 'old-1', 'legacy key still found');

  const { fetchFn } = mockFetch({
    'https://venkateshrao.com/blyg/h/history/': page('History'),
    'https://venkateshrao.com/blyg/blyg.json': json(MANIFEST),
  });
  const r = await revalidate(env, rec, { fetchFn });
  assert.equal(r.record.status, 'approved');
  assert.equal(r.record.decided_by, 'auto-validator');
  assert.equal(r.record.base, 'https://venkateshrao.com/blyg/');
  assert.equal(env.store.get('canon:https://venkateshrao.com/blyg/h/history/'), 'old-1');
  assert.ok(!env.store.has('canon:https://venkateshrao.com/blyg/h/history'));
});

test('revalidate: failure records the error and leaves status alone', async () => {
  const env = memoryEnv();
  const rec = legacy();
  const { fetchFn } = mockFetch({});
  const r = await revalidate(env, rec, { fetchFn });
  assert.equal(r.status, 422);
  assert.equal(r.record.status, 'pending');
  assert.match(JSON.parse(env.store.get('sub:old-1')).validation_error, /404/);
});

test('reject blocks the blyg under either slash spelling', async () => {
  const env = memoryEnv();
  await decide(env, legacy(), 'rejected', 'admin@example.com');
  assert.equal(await isBlocked(env, { base: 'https://venkateshrao.com/blyg/' }), true);
  assert.equal(await isBlocked(env, { base: 'https://venkateshrao.com/blyg' }), true);
  assert.equal(await isBlocked(env, { email: 'v@example.com' }), true);
  assert.equal(await isBlocked(env, { base: 'https://other.example/', email: 'x@example.com' }), false);
});
