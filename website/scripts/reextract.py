#!/usr/bin/env python3
"""
Retry extraction for contributions stored link-only.

Run locally (a home connection usually gets through where GitHub's runners
are challenged), or with INGEST_RELAY_TOKEN set to go through the relay:

    cd website
    python scripts/reextract.py            # dry run: report what would change
    python scripts/reextract.py --write    # update the article JSONs

After `--write`, run scripts/export_contributions.py so the Oracle sees the new text.

Only `type: contribution` entries with an http(s) URL are retried. Resources
stay link-only on purpose (third-party text is not stored), and team-only or
PDF-backed entries are left alone. Slugs never change, so links stay stable.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from article_fetch import fetch_and_extract  # noqa: E402
from ingest import title_from_url  # noqa: E402

ARTICLES = Path(__file__).parent.parent / 'content' / 'articles'


def candidates():
    for path in sorted(ARTICLES.glob('*.json')):
        article = json.loads(path.read_text(encoding='utf-8'))
        url = article.get('url') or ''
        if (article.get('extraction_success')
                or article.get('type') != 'contribution'
                or not url.startswith(('http://', 'https://'))
                or article.get('license') == 'team_only'
                or article.get('pdf_key')):
            continue
        yield path, article


def main():
    write = '--write' in sys.argv[1:]
    fixed = failed = 0
    for path, article in candidates():
        url = article['url']
        print(f"{path.name}\n  {url}")
        title, date, text, ok = fetch_and_extract(url)
        if not ok:
            failed += 1
            print("  still link-only")
            continue
        fixed += 1
        article['extracted_text'] = text
        article['extraction_success'] = True
        if date and not article.get('published_at'):
            article['published_at'] = date
        # Only replace a title that was itself a fallback built from the URL.
        if title and article.get('title') == title_from_url(url):
            article['title'] = title
        print(f"  extracted {len(text)} chars; title={article['title']!r}")
        if write:
            path.write_text(json.dumps(article, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f"\n{fixed} extracted, {failed} still link-only{'' if write else ' (dry run — nothing written)'}")


if __name__ == '__main__':
    main()
