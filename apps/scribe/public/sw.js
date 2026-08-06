// sw.js — offline shell for Scribe.
//
// Network-first everywhere, cache only as a fallback. Cache-first would mean a
// deploy is invisible until the cache version is bumped, which is the classic way
// a PWA ends up serving a stale app.js for a week.
//
// Two tiers:
//   SHELL     the app itself + the baked note index. Precached on install so the
//             app opens (and the [[link]] picker still works) with no network.
//   /api/*    never cached. A failed API call returns a JSON error the UI can show
//             rather than a dead promise — a draft is safe in localStorage either
//             way, so the honest answer is better than a stale one.

const CACHE = "scribe-v1";
const SHELL = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/data/notes-index.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return; // never cache a POST — those are writes
  const url = new URL(e.request.url);

  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request).catch(
        () =>
          new Response(JSON.stringify({ ok: false, error: "offline — your draft is saved on this device" }), {
            status: 503,
            headers: { "content-type": "application/json" },
          })
      )
    );
    return;
  }

  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches
          .open(CACHE)
          .then((c) => c.put(e.request, copy))
          .catch(() => {});
        return res;
      })
      .catch(() => caches.match(e.request).then((hit) => hit || caches.match("/index.html")))
  );
});
