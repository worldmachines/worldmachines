#!/usr/bin/env python3
"""
Process new_writing_inbox.md: ingest each entry, write article JSONs, clear the inbox.
Run from the website/ directory (working-directory in CI).
"""
import datetime
import json
import sys
from pathlib import Path

from ingest import fetch_and_extract, title_from_url, slugify

INBOX = Path(__file__).parent.parent.parent / 'new_writing_inbox.md'
ARTICLES_DIR = Path(__file__).parent.parent / 'content' / 'articles'
VALID_TYPES = {'contribution', 'resource'}


def parse_entries(text):
    entries = []
    after_sep = False
    for line in text.splitlines():
        if line.strip() == '---':
            after_sep = True
            continue
        if not after_sep:
            continue
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 3:
            print(f"  Skipping malformed line: {line!r}", file=sys.stderr)
            continue
        handle, type_, url = parts[0], parts[1], parts[2]
        description = parts[3] if len(parts) > 3 else None
        if type_ not in VALID_TYPES:
            print(f"  Invalid type {type_!r} — skipping {url}", file=sys.stderr)
            continue
        entries.append({'handle': handle, 'type': type_, 'url': url, 'description': description})
    return entries


def cleared_inbox(text):
    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        result.append(line)
        if line.strip() == '---':
            break
    return ''.join(result)


def main():
    text = INBOX.read_text(encoding='utf-8')
    entries = parse_entries(text)

    if not entries:
        print("Inbox is empty — nothing to do.")
        return

    print(f"Processing {len(entries)} inbox entr{'y' if len(entries) == 1 else 'ies'}...")
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    submitted_at = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    for entry in entries:
        url = entry['url']
        handle = entry['handle']
        type_ = entry['type']
        description = entry['description']

        if type_ == 'resource':
            title = title_from_url(url)
            pub_date = None
            extracted_text = None
            success = False
            print(f"  Resource (link-only): {url}")
            print(f"    Title fallback: {title}")
        else:
            print(f"  Ingesting: {url}")
            title, pub_date, extracted_text, success = fetch_and_extract(url)
            if not title:
                title = title_from_url(url)
                print(f"    Title fallback: {title}")
            else:
                print(f"    Title: {title}")
            if pub_date:
                print(f"    Published: {pub_date}")
            print(f"    Extraction: {'success' if success else 'failed (link-only)'}")

        slug = slugify(title, url, submitted_at)
        article = {
            'slug': slug,
            'url': url,
            'title': title,
            'handle': handle,
            'submitted_at': submitted_at,
            'type': type_,
            'format': 'essay',
            'published_at': pub_date,
            'description': description,
            'extraction_success': success,
            'extracted_text': extracted_text,
        }

        out = ARTICLES_DIR / f'{slug}.json'
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(article, f, indent=2, ensure_ascii=False)
        print(f"    Saved: {out.name}")

    INBOX.write_text(cleared_inbox(text), encoding='utf-8')
    print("Inbox cleared.")


if __name__ == '__main__':
    main()
