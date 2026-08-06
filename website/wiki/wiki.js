/* Wiki behaviour: search, and the A-Z filter. No dependencies, no network
   beyond one fetch of the prebuilt index, and every page works without it —
   search degrades to the A-Z list, which is plain HTML.

   The index is [title, url-after-/wiki/, gloss, where, kind]. */
(function () {
  'use strict';

  var KINDS = { definition: 0, note: 1, topic: 2, contributor: 3, book: 3, wanted: 4 };
  var index = null;
  var pending = null;

  function load() {
    if (index) return Promise.resolve(index);
    if (!pending) {
      pending = fetch('/wiki/search-index.json')
        .then(function (r) { return r.ok ? r.json() : { n: [] }; })
        .then(function (data) { index = data.n || []; return index; })
        .catch(function () { index = []; return index; });
    }
    return pending;
  }

  function score(row, q, terms) {
    var title = row[0].toLowerCase();
    var hay = title + ' ' + row[2].toLowerCase() + ' ' + row[3].toLowerCase();
    var s = 0;
    if (title === q) s = 1000;
    else if (title.indexOf(q) === 0) s = 600;
    else if (title.indexOf(q) !== -1) s = 320;
    else if (row[2].toLowerCase().indexOf(q) !== -1) s = 120;
    if (!s) {
      // Every word has to appear somewhere, so "massey place" still finds things.
      for (var i = 0; i < terms.length; i++) {
        if (hay.indexOf(terms[i]) === -1) return 0;
      }
      s = 60;
    }
    return s - (KINDS[row[4]] === undefined ? 2 : KINDS[row[4]]) * 4;
  }

  function search(rows, query, limit) {
    var q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    var terms = q.split(/\s+/);
    var hits = [];
    for (var i = 0; i < rows.length; i++) {
      var s = score(rows[i], q, terms);
      if (s > 0) hits.push([s, rows[i]]);
    }
    hits.sort(function (a, b) {
      if (b[0] !== a[0]) return b[0] - a[0];
      return a[1][0].toLowerCase() < b[1][0].toLowerCase() ? -1 : 1;
    });
    return hits.slice(0, limit).map(function (h) { return h[1]; });
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function href(row) { return '/wiki/' + row[1]; }

  /* ---- toolbar search: instant dropdown ---- */

  var box = document.getElementById('wiki-q');
  var panel = document.getElementById('wiki-q-results');

  if (box && panel) {
    var active = -1;

    function close() { panel.hidden = true; panel.textContent = ''; active = -1; }

    function draw(rows) {
      panel.textContent = '';
      if (!rows.length) {
        panel.appendChild(el('div', 'r-empty', 'No match. Try a different word.'));
        panel.hidden = false;
        return;
      }
      rows.forEach(function (row) {
        var a = el('a', null);
        a.href = href(row);
        var line = el('div', null);
        line.appendChild(el('span', 'r-title', row[0]));
        line.appendChild(el('span', 'r-where', row[3]));
        a.appendChild(line);
        if (row[2]) a.appendChild(el('div', 'r-gloss', row[2]));
        panel.appendChild(a);
      });
      panel.hidden = false;
      active = -1;
    }

    function run() {
      var q = box.value;
      if (q.trim().length < 2) { close(); return; }
      load().then(function (rows) {
        if (box.value !== q) return;   // a later keystroke already won
        draw(search(rows, q, 10));
      });
    }

    box.addEventListener('input', run);
    box.addEventListener('focus', function () { if (box.value.trim().length >= 2) run(); });

    box.addEventListener('keydown', function (e) {
      var items = panel.querySelectorAll('a');
      if (e.key === 'Escape') { close(); box.blur(); return; }
      if (!items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active += (e.key === 'ArrowDown' ? 1 : -1);
        if (active < 0) active = items.length - 1;
        if (active >= items.length) active = 0;
        for (var i = 0; i < items.length; i++) {
          items[i].classList.toggle('is-active', i === active);
        }
        items[active].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();
        window.location.href = items[active].href;
      }
    });

    document.addEventListener('click', function (e) {
      if (!panel.hidden && !panel.contains(e.target) && e.target !== box) close();
    });

    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase();
      if (e.key === '/' && tag !== 'input' && tag !== 'textarea' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        box.focus();
        box.select();
      }
    });
  }

  /* ---- /wiki/search: the full results page ---- */

  var results = document.getElementById('search-results');
  var status = document.getElementById('search-status');

  if (results) {
    var field = document.getElementById('search-q');

    function show(query) {
      if (!query || query.trim().length < 2) {
        results.textContent = '';
        if (status) status.textContent = 'Type at least two letters to search.';
        return;
      }
      load().then(function (rows) {
        var hits = search(rows, query, 80);
        results.textContent = '';
        if (status) {
          status.textContent = hits.length
            ? hits.length + (hits.length === 80 ? '+ matches for ' : ' matches for ') + '“' + query + '”'
            : 'Nothing matches “' + query + '”. The A–Z index lists every note.';
        }
        var list = el('ul', null);
        hits.forEach(function (row) {
          var li = el('li', 'sr-item');
          var a = el('a', null, row[0]);
          a.href = href(row);
          li.appendChild(a);
          li.appendChild(el('span', 'sr-where', row[3]));
          if (row[2]) li.appendChild(el('div', 'sr-gloss', row[2]));
          list.appendChild(li);
        });
        results.appendChild(list);
      });
    }

    var q0 = new URLSearchParams(window.location.search).get('q') || '';
    if (field) {
      field.value = q0;
      field.addEventListener('input', function () { show(field.value); });
    }
    if (box) box.value = q0;
    if (q0) show(q0);
  }

  /* ---- A-Z filter ---- */

  var azFilter = document.getElementById('az-filter');
  if (azFilter) {
    var azCount = document.getElementById('az-count');
    var rows = Array.prototype.slice.call(document.querySelectorAll('.az-row'));
    var blocks = Array.prototype.slice.call(document.querySelectorAll('.az-block'));
    azFilter.addEventListener('input', function () {
      var q = azFilter.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var hit = !q || row.getAttribute('data-search').indexOf(q) !== -1;
        row.hidden = !hit;
        if (hit) shown++;
      });
      blocks.forEach(function (block) {
        block.hidden = !block.querySelector('.az-row:not([hidden])');
      });
      if (azCount) azCount.textContent = shown;
    });
  }
})();
