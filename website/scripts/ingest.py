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
import tempfile
from urllib.parse import urlparse

# Substack API → page → RSS feed, with an honest User-Agent. Re-exported so
# ingest_inbox.py keeps importing it from here.
from article_fetch import fetch_and_extract, fetch_pasted  # noqa: F401
from feed_resource import gate as feed_gate, in_scope as feed_in_scope, normalize


def clean_pasted(text):
    """Browser textareas send CRLF; copying from Substack brings zero-width spaces."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\u200b', '')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


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


def build_article(url, handle, type_, format_, description, submitted_at, pasted_key=None):
    """Fetch and gate one submission. Returns (article, feed_text): feed_text
    is the resource text queued for wm-feeder, or None. Shared by the web form
    (main) and the writing inbox (ingest_inbox.py)."""
    feed_text = None
    skipped = None
    if type_ == 'resource' and not feed_in_scope(type_, format_):
        # Books and other long third-party works: store the link without fetching
        title = title_from_url(url)
        pub_date = None
        text = None
        success = False
        print(f"Resource (no ingestion): {url}")
        print(f"  Title fallback: {title}")
    else:
        print(f"Ingesting: {url}")
        title, pub_date, text, success = fetch_and_extract(url)
        if not title:
            title = title_from_url(url)
            print(f"  Title fallback from URL: {title}")
        else:
            print(f"  Title: {title}")
        if pub_date:
            print(f"  Published: {pub_date}")
        print(f"  Extraction: {'success' if success else 'failed (link-only)'}")
        if type_ == 'resource':
            # Third-party text never enters git. In-cap essays/papers go to the
            # feeder (via R2) for reading notes; the article JSON stays link-only.
            text = normalize(text) if text else text
            skipped = feed_gate(text, success)
            if skipped:
                print(f"  Feeder: skipped ({skipped}, {len(text or '')} chars)")
            else:
                feed_text = text
                print(f"  Feeder: queued ({len(text)} chars)")
            text = None

    # Text the member pasted on /submit wins over extraction: they paste when
    # the page is paywalled or blocked, where extraction gets a teaser at best.
    if pasted_key and type_ != 'resource':
        pasted = clean_pasted(fetch_pasted(pasted_key) or '')
        if pasted:
            text, success = pasted, True
            print(f"  Using pasted text ({len(pasted)} chars)")
        else:
            print(f"  WARNING: pasted text {pasted_key} could not be read")

    slug = slugify(title, url, submitted_at)
    article = {
        'slug': slug,
        'url': url,
        'title': title,
        'handle': handle,
        'submitted_at': submitted_at,
        'type': type_,
        'format': format_,
        'published_at': pub_date,
        'description': description,
        'extraction_success': success,
        'extracted_text': text,
    }
    if feed_text is not None:
        article['ingest_status'] = 'queued'
    elif skipped:
        article['ingest_skipped'] = skipped
    return article, feed_text


def write_feed_text(slug, text):
    """Write queued resource text outside the repo (RUNNER_TEMP in CI) so no
    `git add` can pick it up. Returns the path."""
    text_dir = os.environ.get('FEED_TEXT_DIR') or os.environ.get('RUNNER_TEMP') or tempfile.gettempdir()
    os.makedirs(text_dir, exist_ok=True)
    text_path = os.path.join(text_dir, f'{slug}.txt')
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"  Feeder text: {text_path}")
    return text_path


def main():
    raw = os.environ.get('SUBMISSION_PAYLOAD')
    if not raw:
        print('ERROR: SUBMISSION_PAYLOAD not set', file=sys.stderr)
        sys.exit(1)

    payload = json.loads(raw)
    article, feed_text = build_article(
        payload['url'], payload['handle'], payload['type'],
        payload.get('format') or 'essay', payload.get('description') or None,
        payload['submitted_at'], payload.get('pasted_key'))
    slug = article['slug']

    os.makedirs('content/articles', exist_ok=True)
    out = f'content/articles/{slug}.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(article, f, indent=2, ensure_ascii=False)

    print(f"  Saved: {out}")

    text_path = write_feed_text(slug, feed_text) if feed_text is not None else ''
    write_outputs({
        'feed_queued': 'true' if feed_text is not None else 'false',
        'slug': slug,
        'title': ' '.join(article['title'].split()),
        'kind': article['format'] if feed_text is not None else '',
        'feed_text': text_path,
    })


def write_outputs(outputs):
    """Expose step outputs to GitHub Actions (no-op locally)."""
    path = os.environ.get('GITHUB_OUTPUT')
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as f:
        for k, v in outputs.items():
            f.write(f"{k}={v}\n")


if __name__ == '__main__':
    main()
