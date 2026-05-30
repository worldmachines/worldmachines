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


NAV = '''\
  <nav class="sitenav">
    <a href="/theory">Theory</a>
    <a href="/contributions">Contributions</a>
    <a href="/resources">Resources</a>
    <a href="/contributors">Contributors</a>
    <a href="/devlog">Devlog</a>
    <a href="/oracle">Oracle</a>
    <a href="https://worldmachines.zulipchat.com">Project Chat</a>
  </nav>'''


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
    pdf_html   = (
        f'\n        <a class="badge badge-pdf" href="/api/pdf/{escape(pdf_key)}" target="_blank">PDF</a>'
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
{NAV}
  <main>
{blurb_html}
  </main>
  <!-- built: {built} -->
</body>
</html>
'''
    Path('index.html').write_text(html, encoding='utf-8')
    print('Built index.html — landing page')


def build_contributions(articles):
    items = contribution_items(articles)
    body, script = render_list(items, 'No contributions yet.')
    html = page_shell('Contributions', NAV, body, script=script)
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
        var pdfHtml = a.pdf_key ? '\n        <a class="badge badge-pdf" href="/api/pdf/' + esc(a.pdf_key) + '" target="_blank">PDF</a>' : '';
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
    html = page_shell('Resources', NAV, body, script=script)
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
    html = page_shell('Devlog', NAV, body)
    Path('devlog.html').write_text(html, encoding='utf-8')
    print(f'Built devlog.html — {len(entries)} entry/entries')


def build():
    articles = load_articles()
    build_index(articles)
    build_contributions(articles)
    build_resources(articles)
    build_devlog()


if __name__ == '__main__':
    build()
