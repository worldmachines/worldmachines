#!/usr/bin/env python3
"""
Batch-imports articles from a predefined list into content/articles/.
Skips URLs already present. Runs ingest logic locally (requires trafilatura).
Run from the repo root: python3 scripts/populate.py
"""
import hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import trafilatura

ARTICLES_DIR = Path('content/articles')
BATCH_DATE   = '2026-05-04T00:00:00Z'

ARTICLES = [
    # (url, handle, type)
    ("https://contraptions.venkateshrao.com/p/the-divergence-machine-ii",   "vgr",     "contribution"),
    ("https://contraptions.venkateshrao.com/p/the-divergence-machine",       "vgr",     "contribution"),
    ("https://contraptions.venkateshrao.com/p/the-modernity-machine-iii",    "vgr",     "contribution"),
    ("https://contraptions.venkateshrao.com/p/the-modernity-machine-ii",     "vgr",     "contribution"),
    ("https://contraptions.venkateshrao.com/p/the-modernity-machine",        "vgr",     "contribution"),
    ("https://aneeshsathe.com/the-octotypic-mind/",                          "aneesh",  "contribution"),
    ("https://aneeshsathe.com/how-the-fox-with-the-long-tail-learned-to-play-in-the-dark-forest/", "aneesh", "contribution"),
    ("https://aneeshsathe.com/logic-of-the-thicket-and-the-unsearchable-web/",            "aneesh",  "contribution"),
    ("https://aneeshsathe.com/four-early-modern-tempers-for-a-world-that-can-summon-itself/", "aneesh", "contribution"),
    ("https://aneeshsathe.com/the-architecture-of-resistance/",              "aneesh",  "contribution"),
    ("https://aneeshsathe.com/the-deep-dark-terroir-of-the-soul/",           "aneesh",  "contribution"),
    ("https://pioneeringspirit.xyz/walking-the-world-machines",              "patrick", "contribution"),
    ("https://www.linkandth.ink/p/voltaire-the-entrepreneur",                "ivo",     "contribution"),
    ("https://www.linkandth.ink/p/three-engineers-of-modernity",             "ivo",     "contribution"),
    ("https://notefields.substack.com/p/history-machines-in-the-margins",    "florian", "contribution"),
    ("https://notefields.substack.com/p/the-best-of-all-possible-worlds",    "florian", "contribution"),
    ("https://notefields.substack.com/p/shitty-castles",                     "florian", "contribution"),
    ("https://open.substack.com/pub/seanstevenson/p/de-dramatizing-the-digital?r=yrsx&utm_medium=ios", "sean", "contribution"),
    ("https://open.substack.com/pub/seanstevenson/p/cosmological-adventure?r=yrsx&utm_campaign=post&utm_medium=web", "sean", "contribution"),
    ("https://open.substack.com/chat/posts/a9c3fffe-6960-4297-8134-9b6d8a1b59cc?utm_source=share", "kyle", "contribution"),
]


def existing_urls():
    urls = set()
    if not ARTICLES_DIR.exists():
        return urls
    for p in ARTICLES_DIR.glob('*.json'):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            urls.add(d.get('url', '').rstrip('/'))
        except Exception:
            pass
    return urls


def fetch_and_extract(url):
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None, None, False
    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    title = (metadata.title or '').strip() or None if metadata else None
    return title, text, text is not None


def title_from_url(url):
    path = urlparse(url).path.rstrip('/')
    last = path.split('/')[-1] if path else ''
    return re.sub(r'[-_]+', ' ', last).title() if last else urlparse(url).netloc


def slugify(title, url):
    base = re.sub(r'[^\w\s-]', '', title.lower())
    base = re.sub(r'[\s_-]+', '-', base).strip('-')[:50].rstrip('-') or 'article'
    uid  = hashlib.md5(url.encode()).hexdigest()[:6]
    date = BATCH_DATE[:10].replace('-', '')
    return f"{base}-{date}-{uid}"


def main():
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    done = existing_urls()
    skipped = added = failed = 0

    for url, handle, type_ in ARTICLES:
        clean = url.rstrip('/')
        if clean in done or url in done:
            print(f"  skip  {url}")
            skipped += 1
            continue

        print(f"  fetch {url}")
        title, text, success = fetch_and_extract(url)
        if not title:
            title = title_from_url(url)

        slug = slugify(title, url)
        article = {
            'slug':               slug,
            'url':                url,
            'title':              title,
            'handle':             handle,
            'submitted_at':       BATCH_DATE,
            'type':               type_,
            'description':        None,
            'extraction_success': success,
            'extracted_text':     text,
        }
        out = ARTICLES_DIR / f'{slug}.json'
        out.write_text(json.dumps(article, indent=2, ensure_ascii=False), encoding='utf-8')

        status = 'ok  ' if success else 'noxt'
        print(f"  {status}  [{handle}] {title}")
        if success:
            added += 1
        else:
            failed += 1

    print(f"\nDone: {added} extracted, {failed} link-only, {skipped} skipped")


if __name__ == '__main__':
    main()
