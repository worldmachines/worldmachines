#!/usr/bin/env python3
"""
Reads content/articles/*.json and devlog.md, then regenerates index.html,
contributions.html, resources.html, and devlog.html.
Run locally or as part of the GitHub Actions ingest pipeline.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ARTICLES_DIR = Path('content/articles')
BLURBS_FILE  = Path('blurbs.md')
DEVLOG_FILE  = Path('devlog.md')


# ─── Site navigation ─────────────────────────────────────────────────────────
#
# Five places, not eleven links. Each group whose contents run to more than one
# page carries a second row, drawn in a single slot under the bar: hover or
# keyboard focus on a pointer that can hover, an explicit chevron on one that
# cannot. Styling lives in website/style.css.
#
# This table is duplicated, deliberately and identically, in
# website/scripts/build_wiki.py — the two builders are stdlib-only and must not
# import each other. Change one, change the other, then run both.
#
#   (group id, label, the group's own page, [(href, label), ...])
NAV_GROUPS = [
    ('theory', 'Theory', '/theory', []),
    ('library', 'Library', '/contributions', [
        ('/contributions', 'Contributions'),
        ('/resources', 'Resources'),
        ('/evolution/', 'Evolution field guide'),
    ]),
    ('wiki', 'Wiki', '/wiki/', [
        ('/wiki/', 'Index'),
        ('/wiki/all', 'A–Z'),
        ('/wiki/glossary/', 'Glossary'),
        ('/wiki/topics/', 'Topics'),
        ('/wiki/hubs', 'Most linked'),
        ('/wiki/wanted/', 'Wanted'),
        ('/wiki/special', 'Special'),
        ('/wiki/search', 'Search'),
    ]),
    ('ask', 'Ask', '/oracle', [
        ('/oracle', 'Oracle'),
        ('/mcp', 'MCP access'),
    ]),
    ('club', 'Club', '/contributors', [
        ('/contributors', 'Contributors'),
        ('/devlog', 'Devlog'),
        ('/join', 'Join'),
        ('https://discord.gg/tqUFztN3r', 'Project chat ↗'),
    ]),
]


def sitenav(current='', suppress_current_row=False):
    """The site bar. `current` marks the group you are standing in.

    `suppress_current_row` is for pages that already print that group's row
    themselves — the wiki does — so the group stands open below the bar
    instead of hiding behind a hover.
    """
    items = []
    for gid, label, href, row in NAV_GROUPS:
        show_row = bool(row) and not (suppress_current_row and gid == current)
        classes = 'nav-item'
        if show_row:
            classes += ' has-row'
        if gid == current:
            classes += ' is-current'
        if not show_row:
            items.append(f'      <li class="{classes}">'
                         f'<a class="nav-label" href="{href}">{label}</a></li>')
            continue
        links = '\n'.join(f'          <a href="{h}">{text}</a>' for h, text in row)
        items.append(
            f'      <li class="{classes}" id="nav-{gid}">\n'
            f'        <a class="nav-label" href="{href}">{label}</a>\n'
            f'        <a class="nav-open" href="#nav-{gid}" aria-label="Show {label} links"><i></i></a>\n'
            f'        <a class="nav-shut" href="#" aria-label="Hide {label} links"><i></i></a>\n'
            f'        <div class="nav-row">\n{links}\n        </div>\n'
            f'      </li>'
        )
    body = '\n'.join(items)
    return ('  <nav class="sitenav" aria-label="Main">\n'
            f'    <ul class="nav-bar">\n{body}\n    </ul>\n'
            '  </nav>')


# Pages written by hand still carry a copy of the bar. The generator owns it:
# `build.py` rewrites the block in place so a copy can never drift again.
STATIC_NAV_PAGES = {
    'admin/handles.html': '',
    'contributors.html': 'club',
    'join.html': 'club',
    'mcp.html': 'ask',
    'oracle.html': 'ask',
    'profile.html': '',
    'submit.html': '',
    'supplements/business-of-enlightenment-translations.html': 'library',
    'theory.html': 'theory',
}

SITENAV_BLOCK = re.compile(r'[ \t]*<nav class="sitenav"[^>]*>.*?</nav>', re.DOTALL)


# PROTOCOL RESEARCH webring bar. Kept in sync by hand with the footer block
# in index.html — see website/network.json (our manifest) and
# website/wormhole.js (vendored widget, mounted below against it).
WEBRING_FOOTER = '''\
  <footer>
    <style>
      /* Scoped to the webring footer bar; maps --wormhole-* theme hooks
         onto this site's own design tokens (see :root in style.css). */
      footer {
        max-width: var(--max-width);
        margin: 0 auto 3rem;
        padding-top: 1.4rem;
        border-top: 1px solid var(--border);
      }
      .webring-bar {
        font-family: system-ui, sans-serif;
        font-size: 0.73rem;
        line-height: 1.7;
        color: var(--muted);
        --wormhole-font: system-ui, sans-serif;
        --wormhole-size: 0.73rem;
        --wormhole-fg: var(--muted);
        --wormhole-accent: var(--link);
        --wormhole-bg: transparent;
        --wormhole-border: var(--border);
        --wormhole-overlay-bg: rgba(250, 249, 247, 0.97);
        --wormhole-edge: var(--border);
        --wormhole-node: var(--bg);
        --wormhole-muted: var(--muted);
        --wormhole-card-bg: rgba(250, 249, 247, 0.97);
        --wormhole-card-solid: var(--bg);
      }
      .webring-bar span { color: var(--link); font-weight: 600; }
      .webring-bar ul {
        list-style: none;
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem 0.9rem;
        margin-top: 0.5rem;
        padding: 0;
      }
      .webring-bar li { white-space: nowrap; }
      .webring-bar a {
        color: var(--muted);
        text-decoration: none;
        border-bottom: 1px dotted var(--border);
      }
      .webring-bar a:hover { color: var(--link); border-bottom-color: var(--link); }
      #wormhole { display: block; margin-top: 0.4rem; }
    </style>
    <div class="webring-bar">
      ◆ This <span>PROTOCOL RESEARCH</span> Webring site is maintained by Aneesh Sathe ◆
      <div id="wormhole" data-manifest="/network.json" data-depth="2" data-title="off">
        <!-- Static fallback for no-JS visitors and crawlers: -->
        <ul>
          <li><a href="https://rafael.fyi">rafa.</a></li>
          <li><a href="https://djinna.com/">Djinna</a></li>
          <li><a href="https://sachinbenny.xyz/">Sachin Benny</a></li>
          <li><a href="https://florianlohse.com/">Florian Lohse</a></li>
          <li><a href="https://pioneeringspirit.xyz">Pioneering Spirit</a></li>
          <li><a href="https://slackersmuse.com">Slacker's Muse</a></li>
          <li><a href="https://aneeshsathe.com/">Aneesh Sathe</a></li>
        </ul>
      </div>
    </div>
  </footer>
  <script src="/wormhole.js" defer></script>'''


SORT_CONTROLS = '''\
  <div class="sort-controls">
    <span>Sort by</span>
    <button class="sort-btn active" data-sort="date">Date</button>
    <button class="sort-btn" data-sort="handle">Handle</button>
    <button class="sort-btn" data-sort="format">Format</button>
  </div>'''


SORT_SCRIPT = '''\
  <script>
    (function () {
      function sortBy(key) {
        var ul = document.querySelector('.articles');
        if (!ul) return;
        Array.from(ul.children).sort(function (a, b) {
          var av = a.dataset[key] || '', bv = b.dataset[key] || '';
          return key === 'date' ? bv.localeCompare(av) : av.localeCompare(bv);
        }).forEach(function (li) { ul.appendChild(li); });
        document.querySelectorAll('.sort-btn').forEach(function (btn) {
          btn.classList.toggle('active', btn.dataset.sort === key);
        });
      }
      document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.sort-btn').forEach(function (btn) {
          btn.addEventListener('click', function () { sortBy(btn.dataset.sort); });
        });
      });
    })();
  </script>'''


def load_articles():
    if not ARTICLES_DIR.exists():
        return []
    articles = []
    for p in ARTICLES_DIR.glob('*.json'):
        with open(p, encoding='utf-8') as f:
            articles.append(json.load(f))
    return articles


def contribution_items(articles):
    items = [a for a in articles if a.get('type') == 'contribution']
    items.sort(key=lambda a: a.get('submitted_at', ''), reverse=True)
    return items


OPEN_LICENSES = {'public_domain', 'cc_by', 'cc_by_nc', 'cc_by_sa', 'cc_by_nc_sa', 'cc'}


def resource_items(articles):
    # Exclude team_only: those are served dynamically after auth check
    items = [
        a for a in articles
        if a.get('type', 'resource') == 'resource' and a.get('license') != 'team_only'
    ]
    items.sort(key=lambda a: a.get('submitted_at', ''), reverse=True)
    return items


def render_blurb():
    if not BLURBS_FILE.exists():
        return ''
    text = BLURBS_FILE.read_text(encoding='utf-8').strip()
    paras = []
    for para in text.split('\n\n'):
        para = para.strip()
        if not para:
            continue
        para = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', para)
        para = re.sub(r'\[([^\]]+)\](?!\()', lambda m: f'<a href="/{m.group(1).lower()}">{m.group(1)}</a>', para)
        para = re.sub(r'_([^_]+)_', r'<em>\1</em>', para)
        paras.append(f'    <p>{para}</p>')
    return '\n'.join(paras)


def fmt_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return dt.strftime('%-d %B %Y')
    except Exception:
        return iso[:10]


def escape(s):
    if s is None:
        return ''
    return (s
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))


def render_item(a):
    title  = escape(a.get('title') or a.get('url') or 'Untitled')
    url    = escape(a.get('url') or '')
    # For resources with a known author (e.g. books), show the author; otherwise show submitter handle.
    author = a.get('author') or ''
    by     = escape(author if author else (a.get('handle') or a.get('submitted_by', '')))
    type_  = a.get('type', 'resource')
    fmt    = a.get('format', 'essay')
    badge_class = 'badge-contribution' if type_ == 'contribution' else 'badge-resource'
    badge_label = fmt.title()
    # Use published_at when available, fall back to submitted_at
    date_iso   = a.get('published_at') or a.get('submitted_at', '')
    date       = fmt_date(date_iso)
    desc       = a.get('description') or ''
    title_html = f'<a href="{url}">{title}</a>' if url else title
    desc_html  = f'\n      <p class="article-description">{escape(desc)}</p>' if desc else ''
    pdf_key    = a.get('pdf_key') or ''
    license_   = a.get('license') or ''
    file_label = 'PDF' if pdf_key.endswith('.pdf') else 'Access'
    pdf_html   = (
        f'\n        <a class="badge badge-pdf" href="/api/pdf/{escape(pdf_key)}" target="_blank">{file_label}</a>'
        if pdf_key and license_ in OPEN_LICENSES else ''
    )
    return f'''\
    <li class="article" data-date="{escape(date_iso)}" data-handle="{escape(a.get("handle") or "")}" data-format="{escape(fmt)}">
      <div class="article-meta">
        <span class="badge {badge_class}">{badge_label}</span>
        <span>{date}</span>
        <span>· {by}</span>{pdf_html}
      </div>
      <h2 class="article-title">{title_html}</h2>{desc_html}
    </li>'''


def render_list(items, empty_msg):
    if not items:
        return f'  <p class="empty-state">{empty_msg}</p>', ''
    rows = '\n'.join(render_item(a) for a in items)
    body = f'{SORT_CONTROLS}\n  <ul class="articles">\n{rows}\n  </ul>'
    return body, SORT_SCRIPT


def page_shell(title, nav, body, script=''):
    built = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} — World Machines</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1><a href="/" style="color:inherit">World Machines</a></h1>
    <a href="/submit" class="submit-link">Submit</a>
  </header>
{nav}
  <main>
{body}
  </main>
{script}  <!-- built: {built} -->
</body>
</html>
'''


def build_index(articles):
    blurb = render_blurb()
    blurb_html = f'  <section class="blurb">\n{blurb}\n  </section>' if blurb else ''
    built = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    html = f'''\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>World Machines</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>World Machines</h1>
    <a href="/submit" class="submit-link">Submit</a>
  </header>
{sitenav()}
  <main>
{blurb_html}
  </main>
{WEBRING_FOOTER}
  <!-- built: {built} -->
</body>
</html>
'''
    Path('index.html').write_text(html, encoding='utf-8')
    print('Built index.html — landing page')


def build_contributions(articles):
    items = contribution_items(articles)
    body, script = render_list(items, 'No contributions yet.')
    html = page_shell('Contributions', sitenav('library'), body, script=script)
    Path('contributions.html').write_text(html, encoding='utf-8')
    print(f'Built contributions.html — {len(items)} contribution(s)')


PRIVATE_LIBRARY_HTML = '''\
  <section class="private-library" id="private-library-section" style="display:none">
    <h2 class="private-library-heading">Team Library</h2>
    <ul class="articles" id="private-articles-list"></ul>
  </section>
  <div id="private-library-signin" style="display:none">
    <p class="empty-state">Team library is accessible to project members.
      <a href="/submit">Sign in</a> to view.
    </p>
  </div>'''


PRIVATE_LIBRARY_SCRIPT = '''\
  <script>
    (function () {
      function fmtDate(iso) {
        if (!iso) return '';
        try {
          var d = new Date(iso);
          if (!isNaN(d.getTime())) return d.toLocaleDateString('en-GB', {day: 'numeric', month: 'long', year: 'numeric'});
        } catch (e) {}
        return iso.slice(0, 10) || iso;
      }
      function esc(s) {
        return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function renderItem(a) {
        var title = esc(a.title || a.url || 'Untitled');
        var url = esc(a.url || '');
        var by = esc(a.author || a.handle || '');
        var fmt = a.format || 'book';
        var dateIso = a.published_at || a.submitted_at || '';
        var date = fmtDate(dateIso) || dateIso;
        var titleHtml = url ? '<a href="' + url + '">' + title + '</a>' : title;
        var descHtml = a.description ? '\n      <p class="article-description">' + esc(a.description) + '</p>' : '';
        var fileLabel = a.pdf_key && a.pdf_key.endsWith('.pdf') ? 'PDF' : 'Access';
        var pdfHtml = a.pdf_key ? '\n        <a class="badge badge-pdf" href="/api/pdf/' + esc(a.pdf_key) + '" target="_blank">' + fileLabel + '</a>' : '';
        return '<li class="article" data-date="' + esc(dateIso) + '" data-handle="' + esc(a.handle || '') + '" data-format="' + esc(fmt) + '">'
          + '\n      <div class="article-meta">'
          + '\n        <span class="badge badge-resource">' + fmt.charAt(0).toUpperCase() + fmt.slice(1) + '</span>'
          + '\n        <span>' + date + '</span>'
          + '\n        <span>\xb7 ' + by + '</span>'
          + pdfHtml
          + '\n      </div>'
          + '\n      <h2 class="article-title">' + titleHtml + '</h2>' + descHtml
          + '\n    </li>';
      }
      document.addEventListener('DOMContentLoaded', function () {
        fetch('/api/library/private')
          .then(function (r) {
            if (r.status === 401) {
              document.getElementById('private-library-signin').style.display = '';
              return null;
            }
            if (r.status === 403) {
              return r.json().then(function (d) {
                var el = document.getElementById('private-library-signin');
                var email = d.email ? encodeURIComponent(d.email) : '';
                el.innerHTML = '<p class="empty-state">Team library is for registered contributors. <a href="/join' + (email ? '?email=' + email : '') + '">Request access →</a></p>';
                el.style.display = '';
                return null;
              });
            }
            return r.ok ? r.json() : null;
          })
          .then(function (articles) {
            if (!articles || !articles.length) return;
            var ul = document.getElementById('private-articles-list');
            ul.innerHTML = articles.map(renderItem).join('\n');
            document.getElementById('private-library-section').style.display = '';
          })
          .catch(function () {});
      });
    })();
  </script>'''


def build_resources(articles):
    items = resource_items(articles)
    list_body, sort_script = render_list(items, 'No resources yet.')
    body = list_body + '\n' + PRIVATE_LIBRARY_HTML
    script = sort_script + PRIVATE_LIBRARY_SCRIPT
    html = page_shell('Resources', sitenav('library'), body, script=script)
    Path('resources.html').write_text(html, encoding='utf-8')
    print(f'Built resources.html — {len(items)} resource(s)')


def parse_devlog():
    if not DEVLOG_FILE.exists():
        return []
    text = DEVLOG_FILE.read_text(encoding='utf-8')
    entries = []
    for chunk in re.split(r'^## ', text, flags=re.MULTILINE):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split('\n', 1)
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ''
        if '[trivial]' in header.lower():
            continue
        m = re.match(r'(\d{4}-\d{2}-\d{2})\s*[·•\-]\s*(\S+)', header)
        if not m:
            continue
        entries.append({'date': m.group(1), 'handle': m.group(2), 'body': body})
    return entries


def render_devlog_body(text):
    paras = []
    for para in text.split('\n\n'):
        para = para.strip()
        if not para:
            continue
        para = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', para)
        para = re.sub(r'`([^`]+)`', r'<code>\1</code>', para)
        para = re.sub(r'_([^_]+)_', r'<em>\1</em>', para)
        paras.append(f'    <p>{para}</p>')
    return '\n'.join(paras)


def render_devlog_entry(entry):
    try:
        dt = datetime.strptime(entry['date'], '%Y-%m-%d')
        date_display = dt.strftime('%-d %B %Y')
    except Exception:
        date_display = entry['date']
    body_html = render_devlog_body(entry['body'])
    return (
        f'  <article class="devlog-entry">\n'
        f'    <div class="devlog-meta">{date_display} · {escape(entry["handle"])}</div>\n'
        f'{body_html}\n'
        f'  </article>'
    )


def build_devlog():
    entries = parse_devlog()
    if entries:
        items_html = '\n'.join(render_devlog_entry(e) for e in entries)
        body = (
            '  <p class="devlog-intro">A running log of non-trivial changes, '
            'maintained by contributors.</p>\n'
            '  <div class="devlog">\n'
            f'{items_html}\n'
            '  </div>'
        )
    else:
        body = '  <p class="empty-state">No devlog entries yet.</p>'
    html = page_shell('Devlog', sitenav('club'), body)
    Path('devlog.html').write_text(html, encoding='utf-8')
    print(f'Built devlog.html — {len(entries)} entry/entries')


def sync_static_navs():
    """Rewrite the nav block in every hand-written page that carries one.

    Only the block between <nav class="sitenav"> and its </nav> is touched, so
    the rest of each page is left exactly as its author wrote it.
    """
    changed = []
    for rel, current in sorted(STATIC_NAV_PAGES.items()):
        path = Path(rel)
        if not path.exists():
            print(f'  ! {rel} is listed in STATIC_NAV_PAGES but missing')
            continue
        text = path.read_text(encoding='utf-8')
        replacement = sitenav(current)
        new, hits = SITENAV_BLOCK.subn(lambda _m: replacement, text, count=1)
        if not hits:
            print(f'  ! {rel} has no <nav class="sitenav"> block')
            continue
        if new != text:
            path.write_text(new, encoding='utf-8')
            changed.append(rel)
    print(f'Synced sitenav into {len(changed)} hand-written page(s)'
          + (': ' + ', '.join(changed) if changed else ''))


def build():
    articles = load_articles()
    build_index(articles)
    build_contributions(articles)
    build_resources(articles)
    build_devlog()
    sync_static_navs()


if __name__ == '__main__':
    build()
