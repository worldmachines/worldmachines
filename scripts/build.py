#!/usr/bin/env python3
"""
Reads content/articles/*.json and regenerates index.html.
Run locally or as part of the GitHub Actions ingest pipeline.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ARTICLES_DIR = Path('content/articles')
OUT = Path('index.html')


def load_articles():
    if not ARTICLES_DIR.exists():
        return []
    articles = []
    for p in ARTICLES_DIR.glob('*.json'):
        with open(p, encoding='utf-8') as f:
            articles.append(json.load(f))
    articles.sort(key=lambda a: a.get('submitted_at', ''), reverse=True)
    return articles


def fmt_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return dt.strftime('%-d %B %Y')
    except Exception:
        return iso[:10]


def escape(s):
    return (s
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))


def render_article(a):
    title = escape(a.get('title') or a['url'])
    url = escape(a['url'])
    by = escape(a.get('handle') or a.get('submitted_by', ''))
    type_ = a.get('type', 'resource')
    badge_class = 'badge-contribution' if type_ == 'contribution' else 'badge-resource'
    badge_label = type_.capitalize()
    date = fmt_date(a.get('submitted_at', ''))
    desc = a.get('description') or ''

    desc_html = f'\n      <p class="article-description">{escape(desc)}</p>' if desc else ''

    return f'''\
    <li class="article">
      <div class="article-meta">
        <span class="badge {badge_class}">{badge_label}</span>
        <span>{date}</span>
        <span>· {by}</span>
      </div>
      <h2 class="article-title"><a href="{url}">{title}</a></h2>{desc_html}
    </li>'''


def build():
    articles = load_articles()

    if articles:
        items = '\n'.join(render_article(a) for a in articles)
        body = f'  <ul class="articles">\n{items}\n  </ul>'
    else:
        body = '  <p class="empty-state">No articles yet.</p>'

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
    <p class="tagline">A collaborative collection of psychohistorical models</p>
    <a href="/submit" class="submit-link">Submit</a>
  </header>
  <main>
{body}
  </main>
  <!-- built: {built} ({len(articles)} articles) -->
</body>
</html>
'''
    OUT.write_text(html, encoding='utf-8')
    print(f"Built index.html — {len(articles)} article(s)")


if __name__ == '__main__':
    build()
