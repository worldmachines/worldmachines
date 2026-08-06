/* ---------------------------------------------------------------------
 * Vendored from https://rafael.fyi/wormhole.js (fetched 2026-08-05).
 * Upstream author (rafa, rafael.fyi) publishes this file with an explicit
 * invitation to reuse: "no build step, copy this file to your own site"
 * and "Rewrite the rendering however you like — as long as you publish a
 * network.json, you are in the network." No formal license header is
 * present upstream; this comment records provenance per that invitation.
 * Local changes beyond this notice: URL-scheme hardening only — absolutize()
 * rejects non-http(s) schemes and safeUrl() gates every manifest-derived URL
 * before it reaches an href or window.open (manifests are third-party data).
 * World Machines mounts it at /wormhole.js against our own /network.json.
 * --------------------------------------------------------------------- */
/*!
 * wormhole.js — a portable webring component
 * v0.2.0 · no dependencies · no build step · copy this file to your own site
 *
 * Usage:
 *   <div id="wormhole" data-manifest="/network.json" data-depth="2">
 *     <!-- static <ul> of links: shown when JS is off, crawlable by search engines -->
 *   </div>
 *   <script src="/wormhole.js"></script>
 *
 * Your manifest is read-only and yours alone — nobody can write to it. The
 * constellation extends at RENDER time, not edit time: a visitor's browser reads
 * your file, then the files of the people you list. The graph is a query, not a
 * database. Set data-depth="1" to disable discovery entirely.
 *
 * The protocol is the manifest, not this file. Rewrite the rendering however
 * you like — as long as you publish a network.json, you are in the network.
 */
(function () {
  'use strict';

  var VERSION = '0.2.0';
  var CFG = {
    manifest: '/network.json',
    depth: 2,           // hops out to crawl; 1 = your list only, no discovery
    maxNodes: 50,       // hard cap so a hostile manifest can't run away with the page
    timeout: 2500,      // ms per manifest fetch
    cacheTtl: 600000    // 10 min, sessionStorage
  };

  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------------------------------------------------------- utils */

  function absolutize(url) {
    if (!url) return null;
    try { var u = new URL(url); if (u.protocol === 'http:' || u.protocol === 'https:') return u.href; } catch (e) {}
    try { return new URL('https://' + url).href; } catch (e) {}
    return null;
  }

  // Manifests are third-party data; only http(s) may reach an href or window.open.
  function safeUrl(url) {
    try { var u = new URL(url); if (u.protocol === 'http:' || u.protocol === 'https:') return u.href; } catch (e) {}
    return null;
  }

  // Identity key: scheme-agnostic, www-agnostic, trailing-slash-agnostic.
  function keyOf(url) {
    try {
      var u = new URL(url);
      return u.hostname.toLowerCase().replace(/^www\./, '') + u.pathname.replace(/\/+$/, '');
    } catch (e) {
      return String(url).toLowerCase();
    }
  }

  // Default: <their-origin>/network.json. An explicit "manifest" hint is written
  // by the curator in their own file, so a relative hint resolves against the
  // curator's document (handy for local mirrors); absolute points anywhere.
  function manifestUrlFor(siteUrl, explicit) {
    if (explicit) {
      try { return new URL(explicit, location.href).href; } catch (e) {}
    }
    try { return new URL('/network.json', siteUrl).href; } catch (e) { return null; }
  }

  function prettyName(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return url; }
  }

  // Manifests are third-party text. Never inject them into the card raw.
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function cacheGet(url) {
    try {
      var raw = sessionStorage.getItem('wormhole:' + url);
      if (!raw) return null;
      var box = JSON.parse(raw);
      if (Date.now() - box.t > CFG.cacheTtl) return null;
      return box.v;
    } catch (e) { return null; }
  }

  function cacheSet(url, value) {
    try {
      sessionStorage.setItem('wormhole:' + url, JSON.stringify({ t: Date.now(), v: value }));
    } catch (e) { /* private mode, quota — non-fatal */ }
  }

  function fetchManifest(url) {
    var hit = cacheGet(url);
    if (hit !== null) return Promise.resolve(hit);

    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, CFG.timeout);

    return fetch(url, { signal: ctrl.signal, mode: 'cors', credentials: 'omit' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })   // CORS, 404, timeout — all just "unreachable"
      .then(function (data) {
        clearTimeout(timer);
        cacheSet(url, data);
        return data;
      });
  }

  /* ----------------------------------------------------------------- graph */

  function Graph(rootManifest) {
    this.nodes = {};          // key -> node
    this.order = [];          // insertion order, keeps layout stable
    var site = rootManifest.site || {};
    this.selfKey = keyOf(site.url || location.href);
    this.add({
      url: absolutize(site.url) || location.origin,
      name: site.name || prettyName(location.href),
      blurb: site.blurb || '',
      depth: 0,
      reachable: true
    });
    this.declare(this.selfKey, rootManifest.links || []);
  }

  Graph.prototype.add = function (spec) {
    var key = keyOf(spec.url);
    if (this.nodes[key]) {
      var n = this.nodes[key];
      // Enrich in place: first writer wins on depth, best data wins on labels.
      if (spec.name && !n.namedBySelf) n.name = spec.name;
      if (spec.blurb) n.blurb = spec.blurb;
      if (typeof spec.reachable === 'boolean') n.reachable = spec.reachable;
      return n;
    }
    if (this.order.length >= CFG.maxNodes) return null;
    var node = {
      key: key,
      url: spec.url,
      name: spec.name || prettyName(spec.url),
      blurb: spec.blurb || '',
      note: spec.note || '',
      quote: spec.quote || '',
      source: spec.source || '',
      sourceUrl: spec.sourceUrl || '',
      depth: spec.depth,
      reachable: spec.reachable === true,
      out: [],                       // keys this node declares
      inFrom: []                     // keys that declared this node
    };
    this.nodes[key] = node;
    this.order.push(key);
    return node;
  };

  // Record the links a node declares, creating placeholder nodes for each.
  Graph.prototype.declare = function (fromKey, links) {
    var self = this;
    var from = this.nodes[fromKey];
    if (!from) return [];
    var created = [];
    links.forEach(function (l) {
      var url = absolutize(typeof l === 'string' ? l : l.url);
      if (!url) return;
      var key = keyOf(url);
      if (key === fromKey) return;
      var node = self.nodes[key] || self.add({
        url: url,
        name: (l && l.name) || prettyName(url),
        note: (l && l.note) || '',
        quote: (l && l.quote) || '',
        source: (l && l.source) || '',
        sourceUrl: (l && l.sourceUrl) || '',
        depth: from.depth + 1,
        reachable: false
      });
      if (!node) return;                       // hit the node cap
      if (fromKey === self.selfKey && l && l.name) node.namedBySelf = true;
      // Your own annotations win over anything a neighbour says about them.
      if (fromKey === self.selfKey && l) {
        if (l.note) node.note = l.note;
        if (l.quote) node.quote = l.quote;
        if (l.source) node.source = l.source;
        if (l.sourceUrl) node.sourceUrl = l.sourceUrl;
      }
      if (node.manifestHint == null && l && l.manifest) node.manifestHint = l.manifest;
      if (from.out.indexOf(key) < 0) from.out.push(key);
      if (node.inFrom.indexOf(fromKey) < 0) node.inFrom.push(fromKey);
      created.push(node);
    });
    return created;
  };

  // Undirected edge list with reciprocity flags.
  Graph.prototype.edges = function () {
    var self = this, seen = {}, out = [];
    this.order.forEach(function (a) {
      self.nodes[a].out.forEach(function (b) {
        if (!self.nodes[b]) return;
        var pair = a < b ? a + '|' + b : b + '|' + a;
        if (seen[pair]) return;
        seen[pair] = true;
        var mutual = self.nodes[b].out.indexOf(a) >= 0;
        out.push({ a: a, b: b, mutual: mutual });
      });
    });
    return out;
  };

  /* ----------------------------------------------------------------- crawl */

  // Breadth-first, lazy. Calls onProgress after every manifest resolves so the
  // constellation fills in as it goes instead of blocking on the slowest site.
  function crawl(graph, depth, onProgress) {
    var frontier = graph.nodes[graph.selfKey].out.slice();
    var hop = 1;

    function step() {
      if (hop > depth || !frontier.length) return Promise.resolve();
      var batch = frontier.slice();
      frontier = [];
      return Promise.all(batch.map(function (key) {
        var node = graph.nodes[key];
        if (!node || node.fetched) return Promise.resolve();
        node.fetched = true;
        var murl = manifestUrlFor(node.url, node.manifestHint);
        if (!murl) return Promise.resolve();
        return fetchManifest(murl).then(function (data) {
          if (data && data.site) {
            node.reachable = true;
            if (!node.namedBySelf && data.site.name) node.name = data.site.name;
            if (data.site.blurb) node.blurb = data.site.blurb;
            if (hop < depth) {
              graph.declare(key, data.links || []).forEach(function (n) {
                if (frontier.indexOf(n.key) < 0) frontier.push(n.key);
              });
            }
          }
          onProgress();
        });
      })).then(function () { hop++; return step(); });
    }

    return step();
  }

  /* ---------------------------------------------------------------- layout */

  // Deterministic radial layout. No force simulation: it never jitters, it
  // looks the same on every load, and it costs nothing.
  function layout(graph, W, H) {
    var cx = W / 2, cy = H / 2;
    // Elliptical rings: the stage is wider than it is tall, so circular rings
    // would leave the sides empty and crowd the labels top and bottom.
    var rx1 = W * 0.25, ry1 = H * 0.30;
    var rx2 = W * 0.41, ry2 = H * 0.44;
    var pos = {};
    var ring1 = [], ring2 = [];

    graph.order.forEach(function (k) {
      var d = graph.nodes[k].depth;
      if (d === 0) pos[k] = { x: cx, y: cy };
      else if (d === 1) ring1.push(k);
      else ring2.push(k);
    });

    ring1.forEach(function (k, i) {
      var a = (i / Math.max(ring1.length, 1)) * Math.PI * 2 - Math.PI / 2;
      pos[k] = { x: cx + Math.cos(a) * rx1, y: cy + Math.sin(a) * ry1, angle: a };
    });

    // Second hop sits near whoever introduced it, fanned out so siblings don't stack.
    var bucket = {};
    ring2.forEach(function (k) {
      var parent = graph.nodes[k].inFrom[0];
      (bucket[parent] = bucket[parent] || []).push(k);
    });
    Object.keys(bucket).forEach(function (p) {
      var base = (pos[p] && pos[p].angle != null) ? pos[p].angle : 0;
      var kids = bucket[p];
      var spread = Math.min(0.9, 0.24 * kids.length);
      kids.forEach(function (k, i) {
        var t = kids.length === 1 ? 0 : (i / (kids.length - 1)) - 0.5;
        var a = base + t * spread;
        pos[k] = { x: cx + Math.cos(a) * rx2, y: cy + Math.sin(a) * ry2, angle: a };
      });
    });

    return pos;
  }

  /* -------------------------------------------------------------- styling */

  var CSS = [
    // all:initial walls off the host page's CSS. Custom properties are exempt
    // from `all`, so --wormhole-* still pierces through for theming.
    ':host { all: initial; display: block; }',
    '* { box-sizing: border-box; }',
    '.bar {',
    '  font-family: var(--wormhole-font, ui-monospace, "SF Mono", Menlo, monospace);',
    '  font-size: var(--wormhole-size, 0.72rem);',
    '  color: var(--wormhole-fg, #888);',
    '  background: var(--wormhole-bg, transparent);',
    '  border: 1px solid var(--wormhole-border, rgba(128,128,128,0.3));',
    '  padding: 0.85em 1em; text-align: center; line-height: 1.9;',
    '  letter-spacing: 0.04em;',
    '}',
    '.bar b { font-weight: 400; color: var(--wormhole-accent, #6ee7a0); }',
    '.bar a { color: var(--wormhole-fg, #888); text-decoration: none; border-bottom: 1px dotted currentColor; cursor: pointer; }',
    '.bar a:hover { color: var(--wormhole-accent, #6ee7a0); }',
    '.bar a.explore b { animation: pulse 4s ease-in-out infinite; }',
    '@keyframes pulse { 0%,92%,100% { opacity: 1 } 96% { opacity: 0.3 } }',

    '.overlay {',
    '  position: fixed; inset: 0; z-index: 2147483000;',
    '  background: var(--wormhole-overlay-bg, rgba(6,8,10,0.985));',
    '  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);',
    '  display: flex; flex-direction: column;',
    '  font-family: var(--wormhole-font, ui-monospace, "SF Mono", Menlo, monospace);',
    '  color: var(--wormhole-fg, #9aa);',
    '  animation: fade 0.3s ease;',
    '}',
    '@keyframes fade { from { opacity: 0 } to { opacity: 1 } }',
    '.head { display: flex; align-items: baseline; gap: 1em; padding: 1.1em 1.4em; flex-wrap: wrap; }',
    '.head h2 { margin: 0; font-size: 0.8rem; font-weight: 400; letter-spacing: 0.18em; text-transform: uppercase; color: var(--wormhole-accent, #6ee7a0); }',
    '.head .count { font-size: 0.68rem; opacity: 0.55; }',
    '.head .close { margin-left: 0.6em; cursor: pointer; font-size: 0.7rem; opacity: 0.6; border: 1px solid currentColor; padding: 0.35em 0.7em; }',
    '.head .close:hover { opacity: 1; }',
    '.stage { flex: 1; min-height: 0; position: relative; }',
    'svg { width: 100%; height: 100%; display: block; }',

    '.edge { stroke: var(--wormhole-edge, rgba(160,180,175,0.34)); fill: none; }',
    '.edge.one-way { stroke-dasharray: 3 5; opacity: 0.55; }',
    '.node { cursor: pointer; }',
    '.node circle {',
    '  fill: var(--wormhole-node, #0d1114); stroke: var(--wormhole-accent, #6ee7a0);',
    '  stroke-width: 1.5; transition: r 0.15s ease;',
    '  filter: var(--wormhole-glow, drop-shadow(0 0 5px var(--wormhole-accent, #6ee7a0)));',
    '}',
    '.node.unreachable circle { stroke: var(--wormhole-muted, #55605e); stroke-dasharray: 2 3; filter: none; }',
    '.node.self circle { fill: var(--wormhole-accent, #6ee7a0); stroke: var(--wormhole-accent, #6ee7a0); }',
    '.node text { fill: var(--wormhole-fg, #9aa); font-size: 10px; text-anchor: middle; letter-spacing: 0.05em; }',
    '.node.self text { fill: var(--wormhole-accent, #6ee7a0); }',
    '.node:hover circle { r: 11; }',
    '.node:hover text { fill: var(--wormhole-accent, #6ee7a0); }',
    '.node.enter { animation: pop 0.5s cubic-bezier(.2,1.3,.4,1) backwards; }',
    '@keyframes pop { from { opacity: 0; transform: scale(0.3) } to { opacity: 1; transform: scale(1) } }',

    '.card {',
    '  position: absolute; pointer-events: none; max-width: 300px;',
    // Two layers on purpose. Hosts tend to pass a translucent panel colour for
    // --wormhole-card-bg (3-15% alpha is typical), which would let the node
    // labels behind the card bleed through. The solid layer underneath
    // guarantees opacity; the tint sits on top of it.
    '  background-color: var(--wormhole-card-solid, #0b0e10);',
    '  background-image: linear-gradient(var(--wormhole-card-bg, rgba(12,16,18,0.97)), var(--wormhole-card-bg, rgba(12,16,18,0.97)));',
    '  border: 1px solid var(--wormhole-accent, #6ee7a0);',
    '  padding: 0.75em 0.9em; font-size: 0.7rem; line-height: 1.55;',
    '  opacity: 0; transition: opacity 0.12s ease;',
    '  box-shadow: 0 6px 24px rgba(0,0,0,0.35);',
    '}',
    '.card.on { opacity: 1; pointer-events: auto; }',
    '.card .n { color: var(--wormhole-accent, #6ee7a0); display: block; margin-bottom: 0.2em; }',
    '.card .u { opacity: 0.5; font-size: 0.62rem; word-break: break-all; display: block; margin-bottom: 0.45em; }',
    '.card .note { font-style: italic; opacity: 0.85; }',
    '.card .quote { font-style: italic; opacity: 0.9; display: block; margin: 0.15em 0 0.5em; }',
    '.card .src { display: block; font-size: 0.62rem; opacity: 0.6; }',
    '.card .src a { color: var(--wormhole-accent, #6ee7a0); text-decoration: none; border-bottom: 1px dotted currentColor; }',
    '.card .src a:hover { opacity: 1; }',
    '.card .via { display: block; margin-top: 0.5em; font-size: 0.62rem; opacity: 0.45; }',

    '.legend { display: flex; gap: 1.4em; padding: 0.9em 1.4em 1.2em; font-size: 0.62rem; opacity: 0.5; flex-wrap: wrap; }',
    '.legend i { font-style: normal; margin-right: 0.4em; }',

    '.join-btn { margin-left: auto; cursor: pointer; font-size: 0.66rem; border: 1px solid currentColor; padding: 0.35em 0.7em; opacity: 0.7; }',
    '.join-btn:hover { opacity: 1; color: var(--wormhole-accent, #6ee7a0); }',
    '.joinbox {',
    '  position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);',
    '  width: min(620px, calc(100% - 2.8em)); max-height: calc(100% - 2.8em); overflow-y: auto;',
    '  background-color: var(--wormhole-card-solid, #0b0e10);',
    '  background-image: linear-gradient(var(--wormhole-card-bg, rgba(12,16,18,0.97)), var(--wormhole-card-bg, rgba(12,16,18,0.97)));',
    '  border: 1px solid var(--wormhole-accent, #6ee7a0); padding: 1.4em 1.5em 1.5em;',
    '  box-shadow: 0 10px 40px rgba(0,0,0,0.45); z-index: 5;',
    '  animation: pop 0.25s cubic-bezier(.2,1.3,.4,1);',
    '}',
    '.joinbox h3 { margin: 0 0 0.3em; font-size: 0.72rem; font-weight: 400; letter-spacing: 0.16em; text-transform: uppercase; color: var(--wormhole-accent, #6ee7a0); }',
    '.joinbox p { margin: 0 0 1.3em; font-size: 0.68rem; line-height: 1.7; opacity: 0.7; }',
    '.joinbox .step { margin-bottom: 1.4em; }',
    '.joinbox .step > label { display: block; font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.5; margin-bottom: 0.5em; }',
    '.joinbox pre {',
    '  margin: 0; padding: 0.8em 0.9em; overflow-x: auto; font-size: 0.64rem; line-height: 1.6;',
    '  border: 1px solid var(--wormhole-border-strong, rgba(128,128,128,0.35));',
    '  background: rgba(127,127,127,0.07); white-space: pre; tab-size: 2;',
    '}',
    '.joinbox .copy { margin-top: 0.5em; cursor: pointer; font: inherit; font-size: 0.6rem; letter-spacing: 0.1em;',
    '  text-transform: uppercase; background: transparent; color: inherit; padding: 0.4em 0.9em;',
    '  border: 1px solid currentColor; opacity: 0.6; }',
    '.joinbox .copy:hover { opacity: 1; color: var(--wormhole-accent, #6ee7a0); }',
    '.joinbox .copy.done { opacity: 1; color: var(--wormhole-accent, #6ee7a0); }',
    '.joinbox .close-join { position: absolute; top: 0.9em; right: 1em; cursor: pointer; font-size: 0.7rem; opacity: 0.5; }',
    '.joinbox .close-join:hover { opacity: 1; }',
    '.joinbox .fine { font-size: 0.62rem; opacity: 0.45; margin: 0; line-height: 1.7; }',
    '.joinbox a { color: var(--wormhole-accent, #6ee7a0); }',
    '.hint { padding: 0 1.4em 1.2em; font-size: 0.66rem; opacity: 0.4; max-width: 46em; line-height: 1.7; }'
  ].join('\n');

  /* --------------------------------------------------------------- render */

  function boot(host) {
    var manifestPath = host.getAttribute('data-manifest') || CFG.manifest;
    var depth = parseInt(host.getAttribute('data-depth'), 10);
    if (isNaN(depth)) depth = CFG.depth;
    var manifestUrl;
    try { manifestUrl = new URL(manifestPath, location.href).href; } catch (e) { return; }

    fetchManifest(manifestUrl).then(function (root) {
      if (!root || !root.site) return;   // no manifest → leave the static fallback alone

      var graph = new Graph(root);
      var shadow = host.shadowRoot || host.attachShadow({ mode: 'open' });
      shadow.textContent = '';           // re-mountable
      // A remount orphans any portal from the previous mount.
      document.querySelectorAll('[data-wormhole-portal]').forEach(function (p) { p.remove(); });
      var style = document.createElement('style');
      style.textContent = CSS;
      shadow.appendChild(style);

      var bar = document.createElement('div');
      bar.className = 'bar';
      shadow.appendChild(bar);

      var crawled = false;
      var overlay = null;
      var portal = null;
      var seenOnce = {};
      var raf = null;
      var frozen = false;
      var hideTimer = null;
      var anim = { nodes: [], edges: [], pos: {} };

      function travel(key) {
        var n = graph.nodes[key];
        var dest = n && safeUrl(n.url);
        if (dest) window.open(dest, '_blank', 'noopener');
      }

      // Before any crawl this is your own list; afterwards it spans whatever the
      // network turned out to contain. Same button, wider world.
      function randomTravel() {
        var pool = graph.order.filter(function (k) { return k !== graph.selfKey; });
        if (pool.length) travel(pool[Math.floor(Math.random() * pool.length)]);
      }

      function renderBar() {
        bar.innerHTML = '';
        // data-title="off" for hosts whose surrounding markup already says this.
        if (host.getAttribute('data-title') !== 'off') {
          var label = document.createElement('div');
          label.innerHTML = '◆ this <b>WORMHOLE</b> is maintained by ' +
            graph.nodes[graph.selfKey].name + ' ◆';
          bar.appendChild(label);
        }

        var nav = document.createElement('div');
        nav.append('[ ');
        var explore = document.createElement('a');
        explore.className = 'explore';
        explore.innerHTML = '✦ <b>Explore</b>';
        explore.addEventListener('click', openOverlay);
        nav.appendChild(explore);
        nav.append(' | ');
        var rnd = document.createElement('a');
        rnd.textContent = 'Random';
        rnd.addEventListener('click', randomTravel);
        nav.appendChild(rnd);
        nav.append(' ]');
        bar.appendChild(nav);
      }

      // Theme variables live on the mount element, but the overlay is portalled
      // to <body>, so they have to be carried across by hand.
      var THEME_VARS = ['font', 'size', 'fg', 'accent', 'bg', 'border', 'glow',
                        'overlay-bg', 'edge', 'node', 'muted', 'card-bg'];

      function makePortal() {
        // position:fixed resolves against the nearest transformed ancestor, not
        // the viewport. Host pages do scroll-reveal transforms all the time, so
        // rendering the overlay inside the mount is a coin flip. Portal to body.
        var el = document.createElement('div');
        el.setAttribute('data-wormhole-portal', '');
        var cs = getComputedStyle(host);
        THEME_VARS.forEach(function (v) {
          var val = cs.getPropertyValue('--wormhole-' + v);
          if (val) el.style.setProperty('--wormhole-' + v, val.trim());
        });
        document.body.appendChild(el);
        var sh = el.attachShadow({ mode: 'open' });
        var st = document.createElement('style');
        st.textContent = CSS;
        sh.appendChild(st);
        portal = el;
        return sh;
      }

      function openOverlay() {
        if (overlay) return;
        var portalShadow = makePortal();
        overlay = document.createElement('div');
        overlay.className = 'overlay';
        overlay.innerHTML =
          '<div class="head">' +
            '<h2>Constellation</h2>' +
            '<span class="count"></span>' +
            '<span class="join-btn">⧉ link back</span>' +
            '<span class="close">close ×</span>' +
          '</div>' +
          '<div class="stage">' +
            '<svg viewBox="0 0 1000 620" preserveAspectRatio="xMidYMid meet"></svg>' +
            '<div class="card"></div>' +
          '</div>' +
          '<div class="legend">' +
            '<span><i>—</i>mutual link</span>' +
            '<span><i>···</i>one-way</span>' +
            '<span><i>◌</i>no manifest found</span>' +
            '<span>click a node to travel</span>' +
          '</div>' +
          '<p class="hint"></p>';
        portalShadow.appendChild(overlay);
        overlay.querySelector('.close').addEventListener('click', closeOverlay);
        overlay.querySelector('.join-btn').addEventListener('click', openJoin);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) closeOverlay(); });
        document.addEventListener('keydown', onKey);

        draw();
        startDrift();
        // Crawl only on open — never on page load. Visitors shouldn't ping
        // third-party origins just because they scrolled to your footer.
        if (!crawled && depth > 1) {
          crawled = true;
          crawl(graph, depth, draw);
        }
      }

      function closeOverlay() {
        if (!overlay) return;
        stopDrift();
        overlay.remove();
        overlay = null;
        if (portal) { portal.remove(); portal = null; }
        document.removeEventListener('keydown', onKey);
      }

      function onKey(e) {
        if (e.key !== 'Escape') return;
        var box = overlay && overlay.querySelector('.joinbox');
        if (box) { box.remove(); return; }   // Esc backs out of the panel first
        closeOverlay();
      }

      /* -------------------------------------------------------- link back */

      function copyText(str, btn) {
        function done() {
          var was = btn.textContent;
          btn.textContent = 'copied ✓';
          btn.classList.add('done');
          setTimeout(function () { btn.textContent = was; btn.classList.remove('done'); }, 1600);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(str).then(done, function () { fallback(); });
        } else { fallback(); }
        function fallback() {
          // clipboard API needs a secure context; plenty of personal sites aren't
          var ta = document.createElement('textarea');
          ta.value = str;
          ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand('copy'); done(); } catch (e) { ta.remove(); return; }
          ta.remove();
        }
      }

      function openJoin() {
        if (!overlay || overlay.querySelector('.joinbox')) return;
        var me = graph.nodes[graph.selfKey];
        var origin, myUrl = me.url;
        try {
          var u = new URL(me.url);
          origin = u.origin;
          if (u.pathname === '/' && !u.search && !u.hash) myUrl = origin;  // no bare trailing slash
        } catch (e) { origin = me.url; }

        // Snippets describe whoever deployed this component, not its author —
        // so a copied wormhole hands out the copier's own details.
        var entry =
          '{\n' +
          '  "url": ' + JSON.stringify(myUrl) + ',\n' +
          '  "name": ' + JSON.stringify(me.name) + ',\n' +
          '  "note": "why they are in your ring"\n' +
          '}';

        var embed =
          '<div id="wormhole" data-manifest="/network.json" data-depth="2">\n' +
          '  <!-- static fallback: your links, for no-JS visitors and crawlers -->\n' +
          '</div>\n' +
          '<script src="/wormhole.js"><' + '/script>';

        var box = document.createElement('div');
        box.className = 'joinbox';
        box.innerHTML =
          '<span class="close-join">×</span>' +
          '<h3>Link back</h3>' +
          '<p>There is no registry and nobody to ask. Publish a <code>network.json</code> ' +
          'and you are in the network — everything else is yours to change.</p>' +

          '<div class="step">' +
            '<label>1 · add this entry to your network.json</label>' +
            '<pre>' + esc(entry) + '</pre>' +
            '<button class="copy" data-copy="entry">copy entry</button>' +
          '</div>' +

          '<div class="step">' +
            '<label>2 · optional — use this component too</label>' +
            '<pre>' + esc(embed) + '</pre>' +
            '<button class="copy" data-copy="embed">copy embed</button>' +
          '</div>' +

          '<p class="fine">Save <a href="' + esc(origin) + '/wormhole.js" target="_blank" rel="noopener">' +
          esc(origin) + '/wormhole.js</a> to your own server rather than linking to it — ' +
          'hotlinking makes someone else\'s uptime your problem. The manifest format is ' +
          'documented at <a href="' + esc(origin) + '/network.json" target="_blank" rel="noopener">' +
          esc(origin) + '/network.json</a>. Serve yours with ' +
          '<code>Access-Control-Allow-Origin: *</code> so other people\'s browsers can read it.</p>';

        box.querySelector('.close-join').addEventListener('click', function () { box.remove(); });
        box.querySelectorAll('.copy').forEach(function (b) {
          b.addEventListener('click', function () {
            copyText(b.getAttribute('data-copy') === 'entry' ? entry : embed, b);
          });
        });
        overlay.querySelector('.stage').appendChild(box);
      }

      /* ------------------------------------------------------------ drift */

      // Slow deterministic wander. Amplitude is small enough that nodes stay
      // where you expect them, and the whole field freezes on hover so you're
      // never chasing a moving target.
      function startDrift() {
        if (REDUCED || raf) return;
        var t0 = performance.now();
        (function frame(now) {
          raf = requestAnimationFrame(frame);
          if (frozen) return;
          var t = (now - t0) / 1000;
          anim.nodes.forEach(function (n) {
            n.dx = Math.sin(t * n.s1 + n.p1) * n.amp;
            n.dy = Math.cos(t * n.s2 + n.p2) * n.amp;
            n.g.setAttribute('transform', 'translate(' + (n.x + n.dx) + ',' + (n.y + n.dy) + ')');
          });
          anim.edges.forEach(function (e) {
            var a = anim.pos[e.a], b = anim.pos[e.b];
            if (!a || !b) return;
            e.line.setAttribute('x1', a.x + (a.dx || 0));
            e.line.setAttribute('y1', a.y + (a.dy || 0));
            e.line.setAttribute('x2', b.x + (b.dx || 0));
            e.line.setAttribute('y2', b.y + (b.dy || 0));
          });
        })(t0);
      }

      function stopDrift() {
        if (raf) cancelAnimationFrame(raf);
        raf = null;
      }

      /* ------------------------------------------------------------- draw */

      function draw() {
        if (!overlay) return;
        var svg = overlay.querySelector('svg');
        var card = overlay.querySelector('.card');

        function hideCard() {
          frozen = false;
          card.classList.remove('on');
        }
        // The card is interactive (it holds a link), so keep it alive while the
        // pointer is on it — and keep the field frozen so it can't drift away.
        card.onmouseenter = function () { clearTimeout(hideTimer); frozen = true; };
        card.onmouseleave = function () { hideTimer = setTimeout(hideCard, 160); };

        var W = 1000, H = 620;
        var pos = layout(graph, W, H);
        var NS = 'http://www.w3.org/2000/svg';
        svg.textContent = '';
        anim = { nodes: [], edges: [], pos: {} };

        graph.edges().forEach(function (e) {
          if (!pos[e.a] || !pos[e.b]) return;
          var line = document.createElementNS(NS, 'line');
          line.setAttribute('x1', pos[e.a].x); line.setAttribute('y1', pos[e.a].y);
          line.setAttribute('x2', pos[e.b].x); line.setAttribute('y2', pos[e.b].y);
          line.setAttribute('class', 'edge' + (e.mutual ? '' : ' one-way'));
          svg.appendChild(line);
          anim.edges.push({ line: line, a: e.a, b: e.b });
        });

        graph.order.forEach(function (key, i) {
          var n = graph.nodes[key], p = pos[key];
          if (!p) return;

          // Outer group carries position (driven by rAF); inner group carries
          // the entry animation, so scale and translate never fight.
          var holder = document.createElementNS(NS, 'g');
          holder.setAttribute('transform', 'translate(' + p.x + ',' + p.y + ')');

          var g = document.createElementNS(NS, 'g');
          var cls = 'node' + (n.depth === 0 ? ' self' : '') + (n.reachable ? '' : ' unreachable');
          if (!seenOnce[key]) { cls += ' enter'; seenOnce[key] = true; }
          g.setAttribute('class', cls);
          g.style.animationDelay = (i * 0.04) + 's';

          var c = document.createElementNS(NS, 'circle');
          c.setAttribute('r', n.depth === 0 ? 12 : n.depth === 1 ? 8 : 5.5);
          g.appendChild(c);

          var t = document.createElementNS(NS, 'text');
          t.setAttribute('y', (n.depth === 0 ? 28 : 22));
          t.textContent = n.name.length > 22 ? n.name.slice(0, 21) + '…' : n.name;
          g.appendChild(t);

          var state = {
            g: holder, x: p.x, y: p.y, dx: 0, dy: 0,
            amp: n.depth === 0 ? 2.5 : n.depth === 1 ? 5 : 6.5,
            s1: 0.13 + (i % 5) * 0.021,
            s2: 0.11 + (i % 7) * 0.017,
            p1: i * 1.7, p2: i * 2.3
          };
          anim.nodes.push(state);
          anim.pos[key] = state;

          g.addEventListener('mouseenter', function () {
            clearTimeout(hideTimer);
            frozen = true;
            var via = n.inFrom.filter(function (k) { return k !== graph.selfKey && graph.nodes[k]; })
                              .map(function (k) { return graph.nodes[k].name; });
            card.innerHTML =
              '<span class="n">' + esc(n.name) + '</span>' +
              '<span class="u">' + esc(n.url) + '</span>' +
              (n.blurb ? '<span>' + esc(n.blurb) + '</span>' : '') +
              (n.quote ? '<span class="quote">“' + esc(n.quote) + '”</span>' : '') +
              (n.source ? '<span class="src">— ' + (safeUrl(n.sourceUrl)
                  ? '<a href="' + esc(safeUrl(n.sourceUrl)) + '" target="_blank" rel="noopener">' + esc(n.source) + '</a>'
                  : esc(n.source)) + '</span>' : '') +
              (n.note ? '<div class="note">' + esc(n.note) + '</div>' : '') +
              (via.length ? '<span class="via">vouched for by ' + esc(via.join(', ')) + '</span>' : '') +
              (n.reachable || n.depth === 0 ? '' : '<span class="via">no manifest — listed, not verified</span>');

            // Flip to the left of the node when it would otherwise run off the
            // right edge, so the card never covers the labels it sits beside.
            var rect = overlay.querySelector('.stage').getBoundingClientRect();
            var cw = 300;
            var nx = ((p.x + state.dx) / W) * rect.width;
            var ny = ((p.y + state.dy) / H) * rect.height;
            var left = nx + 18;
            if (left + cw > rect.width - 8) left = Math.max(8, nx - cw - 18);
            card.style.left = left + 'px';
            card.style.top = Math.max(8, Math.min(ny - 20, rect.height - 160)) + 'px';
            card.classList.add('on');
          });
          g.addEventListener('mouseleave', function () {
            // Grace period so the pointer can travel to the card and click the
            // source link without the card vanishing underneath it.
            hideTimer = setTimeout(hideCard, 260);
          });
          g.addEventListener('click', function () { if (n.depth !== 0) travel(key); });

          holder.appendChild(g);
          svg.appendChild(holder);
        });

        var reached = graph.order.filter(function (k) { return graph.nodes[k].reachable; }).length;
        var mine = graph.nodes[graph.selfKey].out.length;
        var discovered = graph.order.length - 1 - mine;
        overlay.querySelector('.count').textContent =
          mine + ' in your ring · ' + discovered + ' discovered · ' + reached + ' publishing a manifest';

        overlay.querySelector('.hint').textContent = depth < 2
          ? 'Discovery is off (depth 1). You are seeing only the sites you list.'
          : discovered > 0
            ? 'The outer ring is not your list. Those sites are vouched for by the people you link, read live from their manifests — they appear and disappear as your neighbours edit their own files.'
            : 'Nobody you link publishes a manifest yet, so there is no outer ring to read. Dotted nodes are listed but unverified.';
      }

      renderBar();
      host.setAttribute('data-wormhole', VERSION);
    });
  }

  function init() {
    var hosts = document.querySelectorAll('[data-wormhole-mount], #wormhole');
    Array.prototype.forEach.call(hosts, boot);
  }

  window.Wormhole = { mount: boot, version: VERSION };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
