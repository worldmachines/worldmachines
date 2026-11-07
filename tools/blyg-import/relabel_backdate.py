#!/usr/bin/env python3
"""
SQL that moves a batch of republished items' new versions back next to their
previous versions, so a mass relabel (e.g. the 2026-11 AI bylines) doesn't flood
feed.xml or the latest-posts list.

For each item id given: its newest version's published_at becomes the previous
version's published_at + 1 second (pinned_at likewise, if set), and items.updated
becomes the newest published_at. Only versions published at or after --since are
touched, so a re-run, or an item somebody else republished earlier, is left alone.
Studio's change_state triggers fire on these UPDATEs, so the feed and HTML caches
rebuild by themselves (blygger-studio's answer of 2026-11-01).

Usage:
  python3 tools/blyg-import/relabel_backdate.py --ids batch.txt --since 2026-11-06T22:00:00Z > batch.sql
  wrangler d1 execute <db> --remote --config wrangler.private.jsonc --file batch.sql
"""
import argparse
import re
import sys
from pathlib import Path

ID = re.compile(r'^[0-9a-z]{26}$')
STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


def build_sql(ids, since):
    if not STAMP.match(since):
        raise ValueError(f'--since must look like 2026-11-06T22:00:00Z, got {since!r}')
    ids = sorted(set(ids))
    bad = [i for i in ids if not ID.match(i)]
    if bad:
        raise ValueError(f'not item ids: {bad[:5]}')
    if not ids:
        return ''
    values = ',\n '.join(f"('{i}')" for i in ids)
    prev = ("(SELECT p.published_at FROM versions p WHERE p.item_id = versions.item_id "
            "AND p.version = versions.version - 1)")
    newest = "(SELECT max(m.version) FROM versions m WHERE m.item_id = versions.item_id)"
    return f"""-- relabel backdate: {len(ids)} item(s), versions published since {since}
CREATE TABLE _relabel (item_id TEXT PRIMARY KEY);
INSERT INTO _relabel (item_id) VALUES
 {values};
UPDATE versions SET
 published_at = strftime('%Y-%m-%dT%H:%M:%SZ', {prev}, '+1 seconds'),
 pinned_at = CASE WHEN pinned_at IS NULL THEN NULL
                  ELSE strftime('%Y-%m-%dT%H:%M:%SZ', {prev}, '+1 seconds') END
 WHERE item_id IN (SELECT item_id FROM _relabel)
   AND version > 1
   AND version = {newest}
   AND published_at >= '{since}'
   AND {prev} IS NOT NULL;
UPDATE items SET updated = (SELECT max(v.published_at) FROM versions v WHERE v.item_id = items.id)
 WHERE id IN (SELECT item_id FROM _relabel);
DROP TABLE _relabel;
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ids', type=Path, required=True, help='file with one item id per line')
    ap.add_argument('--since', required=True, help='batch start, UTC, e.g. 2026-11-06T22:00:00Z')
    a = ap.parse_args(argv)
    ids = [l.strip() for l in a.ids.read_text().splitlines() if l.strip()]
    sys.stdout.write(build_sql(ids, a.since))
    return 0


if __name__ == '__main__':
    sys.exit(main())
