#!/usr/bin/env python3
"""
Reads content/articles/*.json and regenerates index.html, contributions.html,
and resources.html. Run locally or as part of the GitHub Actions ingest pipeline.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ARTICLES_DIR = Path('content/articles')
BLURBS_FILE  = Path('blurbs.md')


NAV = '''\
  <nav class="sitenav">
    <a href="/theory">Theory</a>
    <a href="/contributions">Contributions</a>
    <a href="/resources">Resources</a>
    <a href="/contributors">Contributors</a>
    <a href="/oracle">Oracle</a>
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


def resource_items(articles):
    items = [a for a in articles if a.get('type', 'resource') == 'resource']
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
    date        = fmt_date(a.get('submitted_at', ''))
    desc        = a.get('description') or ''
    title_html  = f'<a href="{url}">{title}</a>' if url else title
    desc_html   = f'\n      <p class="article-description">{escape(desc)}</p>' if desc else ''
    return f'''\
    <li class="article" data-date="{escape(a.get("submitted_at", ""))}" data-handle="{escape(a.get("handle") or "")}" data-format="{escape(fmt)}">
      <div class="article-meta">
        <span class="badge {badge_class}">{badge_label}</span>
        <span>{date}</span>
        <span>· {by}</span>
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


def build_resources(articles):
    items = resource_items(articles)
    body, script = render_list(items, 'No resources yet.')
    html = page_shell('Resources', NAV, body, script=script)
    Path('resources.html').write_text(html, encoding='utf-8')
    print(f'Built resources.html — {len(items)} resource(s)')


def build():
    articles = load_articles()
    build_index(articles)
    build_contributions(articles)
    build_resources(articles)


if __name__ == '__main__':
    build()
