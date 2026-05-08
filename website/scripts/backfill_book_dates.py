#!/usr/bin/env python3
"""
Looks up first publication year for book stubs via Open Library search API.
Stores the year as published_at (e.g. "1759").
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ARTICLES_DIR = Path('content/articles')
OL_SEARCH    = 'https://openlibrary.org/search.json'


def first_pub_year(title, author):
    params = urllib.parse.urlencode({
        'title':  title,
        'author': author,
        'limit':  1,
        'fields': 'title,author_name,first_publish_year',
    })
    req = urllib.request.Request(
        f'{OL_SEARCH}?{params}',
        headers={'User-Agent': 'worldmachines-date-lookup/1.0'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        docs = data.get('docs', [])
        if docs:
            year = docs[0].get('first_publish_year')
            return str(year) if year else None
    except Exception as e:
        print(f'  error: {e}')
    return None


def main():
    paths   = sorted(ARTICLES_DIR.glob('*.json'))
    updated = skipped = not_found = 0

    for p in paths:
        with open(p, encoding='utf-8') as f:
            a = json.load(f)

        if a.get('format') != 'book':
            continue

        if a.get('published_at'):
            print(f'skip (already set):  {a["title"]}')
            skipped += 1
            continue

        title  = a.get('title', '')
        author = a.get('author', '')
        print(f'looking up: {title} — {author}')

        year = first_pub_year(title, author)

        if year:
            a['published_at'] = year
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(a, f, indent=2, ensure_ascii=False)
            print(f'  → {year}')
            updated += 1
        else:
            print(f'  → not found')
            not_found += 1

        time.sleep(0.35)

    print(f'\nDone: {updated} updated, {not_found} not found, {skipped} skipped')


if __name__ == '__main__':
    main()
