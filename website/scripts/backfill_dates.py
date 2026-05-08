#!/usr/bin/env python3
"""
Backfills published_at for article JSONs that have a URL but no published_at.
Fetches each URL and extracts the publication date via trafilatura metadata.
"""
import json
import time
from pathlib import Path

import trafilatura

ARTICLES_DIR = Path('content/articles')


def extract_date(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        metadata = trafilatura.extract_metadata(downloaded)
        return (metadata.date or '').strip() or None
    except Exception as e:
        print(f'  error: {e}')
        return None


def main():
    paths = sorted(ARTICLES_DIR.glob('*.json'))
    updated = skipped = no_date = 0

    for p in paths:
        with open(p, encoding='utf-8') as f:
            a = json.load(f)

        title = a.get('title') or p.stem
        url   = a.get('url')

        if not url:
            print(f'skip (no url):       {title}')
            skipped += 1
            continue

        if a.get('published_at'):
            print(f'skip (already set):  {title}')
            skipped += 1
            continue

        print(f'fetching: {url[:80]}')
        date = extract_date(url)

        if date:
            a['published_at'] = date
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(a, f, indent=2, ensure_ascii=False)
            print(f'  → {date}  ({title})')
            updated += 1
        else:
            print(f'  → no date found  ({title})')
            no_date += 1

        time.sleep(0.5)

    print(f'\nDone: {updated} updated, {no_date} no date found, {skipped} skipped')


if __name__ == '__main__':
    main()
