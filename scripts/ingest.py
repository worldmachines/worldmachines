#!/usr/bin/env python3
"""
Triggered by GitHub Actions on article-submission dispatch.
Reads SUBMISSION_PAYLOAD env var, fetches + extracts the article, writes content/articles/<slug>.json.
"""
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlparse

import trafilatura


def fetch_and_extract(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        return None, None, False
    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    title = (metadata.title or '').strip() or None
    return title, text, text is not None


def title_from_url(url):
    path = urlparse(url).path.rstrip('/')
    last = path.split('/')[-1] if path else ''
    if last:
        return re.sub(r'[-_]+', ' ', last).title()
    return urlparse(url).netloc


def slugify(title, url, submitted_at):
    base = re.sub(r'[^\w\s-]', '', title.lower())
    base = re.sub(r'[\s_-]+', '-', base).strip('-')[:50].rstrip('-') or 'article'
    date = submitted_at[:10].replace('-', '')
    uid = hashlib.md5(url.encode()).hexdigest()[:6]
    return f"{base}-{date}-{uid}"


def main():
    raw = os.environ.get('SUBMISSION_PAYLOAD')
    if not raw:
        print('ERROR: SUBMISSION_PAYLOAD not set', file=sys.stderr)
        sys.exit(1)

    payload = json.loads(raw)
    url = payload['url']
    handle = payload['handle']
    type_ = payload['type']
    format_ = payload.get('format') or 'essay'
    description = payload.get('description') or None
    submitted_at = payload['submitted_at']

    if type_ == 'resource':
        # Resources are third-party — store the link without fetching
        title = title_from_url(url)
        text = None
        success = False
        print(f"Resource (no ingestion): {url}")
        print(f"  Title fallback: {title}")
    else:
        print(f"Ingesting: {url}")
        title, text, success = fetch_and_extract(url)
        if not title:
            title = title_from_url(url)
            print(f"  Title fallback from URL: {title}")
        else:
            print(f"  Title: {title}")
        print(f"  Extraction: {'success' if success else 'failed (link-only)'}")

    slug = slugify(title, url, submitted_at)
    article = {
        'slug': slug,
        'url': url,
        'title': title,
        'handle': handle,
        'submitted_at': submitted_at,
        'type': type_,
        'format': format_,
        'description': description,
        'extraction_success': success,
        'extracted_text': text,
    }

    os.makedirs('content/articles', exist_ok=True)
    out = f'content/articles/{slug}.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(article, f, indent=2, ensure_ascii=False)

    print(f"  Saved: {out}")


if __name__ == '__main__':
    main()
