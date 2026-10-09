#!/usr/bin/env python3
"""
Process new_writing_inbox.md: ingest each entry, write article JSONs, clear the inbox.
Run from the website/ directory (working-directory in CI).
"""
import datetime
import json
import sys
from pathlib import Path

from ingest import build_article, write_feed_text, write_outputs

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

    feed = []
    for entry in entries:
        # Inbox lines carry no format; resources are treated as essays, so
        # wm-feeder reads any third-party link within the length cap.
        article, feed_text = build_article(
            entry['url'], entry['handle'], entry['type'], 'essay',
            entry['description'], submitted_at)

        out = ARTICLES_DIR / f"{article['slug']}.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(article, f, indent=2, ensure_ascii=False)
        print(f"    Saved: {out.name}")

        if feed_text is not None:
            write_feed_text(article['slug'], feed_text)
            feed.append(article['slug'])

    INBOX.write_text(cleared_inbox(text), encoding='utf-8')
    print("Inbox cleared.")
    # JSON list for the workflow's per-slug feed matrix.
    write_outputs({'feed_slugs': json.dumps(feed)})


if __name__ == '__main__':
    main()
