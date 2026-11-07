#!/usr/bin/env python3
"""
Keep the World Machines blyg's address book in step with tools/blyg-import/authors.json.

Studio 0.55+ turns an `@handle` in a post into a link and an h-card when the
handle names a contact in its address book (studio-private; nothing is sent).
Every member in authors.json who has a blyg becomes a contact:
  handle = their authors.json key (aneesh, venkat, florian, ...), plus any
           handle aliases listed for them under "handles"
  name   = their name, url = their blyg
Existing contacts with the same handle are updated when the name or url
differs; contacts this script did not make are never touched or deleted. After
a create or a url change it asks Studio to resolve the contact (reads the
blyg's manifest to bind its identifiers).

Usage (from website/):
  python scripts/blyg_contacts.py            # dry run: print the plan
  python scripts/blyg_contacts.py --execute  # write

Environment: BLYG_MANAGE_TOKEN (owner:manage), BLYG_API_BASE (default
https://blyg.worldmachines.org/api). Stdlib only.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blyg_sync import BlygApi, BlygError, urllib_transport  # noqa: E402

AUTHORS_PATH = HERE.parent.parent / 'tools' / 'blyg-import' / 'authors.json'
DEFAULT_API_BASE = 'https://blyg.worldmachines.org/api'
HANDLE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$')


def wanted_contacts(authors):
    """[{handle, name, url}] for every member with a blyg."""
    out = []
    for key, who in sorted((authors.get('authors') or {}).items()):
        url = (who.get('blyg') or '').strip()
        name = (who.get('name') or '').strip()
        if not url or not name or not HANDLE.match(key):
            continue
        out.append({'handle': key, 'name': name, 'url': url})
    return out


def plan(wanted, existing):
    """(creates, updates[(id, fields)]) to bring `existing` contacts up to `wanted`, by handle."""
    by_handle = {c.get('handle'): c for c in existing}
    creates, updates = [], []
    for w in wanted:
        have = by_handle.get(w['handle'])
        if have is None:
            creates.append(w)
            continue
        fields = {k: w[k] for k in ('name', 'url') if (have.get(k) or '') != w[k]}
        if fields:
            updates.append((have['id'], fields))
    return creates, updates


def main(argv=None, transport=urllib_transport):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--execute', action='store_true', help='write to the blyg (default: dry run)')
    p.add_argument('--authors', default=str(AUTHORS_PATH))
    a = p.parse_args(argv)
    authors = json.loads(Path(a.authors).read_text())
    token = os.environ.get('BLYG_MANAGE_TOKEN')
    if not token:
        print('BLYG_MANAGE_TOKEN is not set (needs owner:manage).', file=sys.stderr)
        return 2
    api = BlygApi(os.environ.get('BLYG_API_BASE') or DEFAULT_API_BASE, token, transport=transport,
                  dry_run=not a.execute)
    existing = api.get('/contacts').get('contacts') or []
    creates, updates = plan(wanted_contacts(authors), existing)
    print(f'contacts: {len(existing)} existing, {len(creates)} to create, {len(updates)} to update')
    for c in creates:
        print(f"  + @{c['handle']}: {c['name']} <{c['url']}>")
    for cid, fields in updates:
        print(f'  ~ {cid}: {fields}')
    if not a.execute:
        print('Dry run: nothing written. Add --execute.')
        return 0
    for c in creates:
        made = api.request('POST', '/contacts', c)[1]
        try:
            api.request('POST', f"/contacts/{made['id']}/resolve")
        except BlygError as e:
            print(f"  ! resolve @{c['handle']}: {e}")
    for cid, fields in updates:
        api.request('PATCH', f'/contacts/{cid}', fields)
        if 'url' in fields:
            try:
                api.request('POST', f'/contacts/{cid}/resolve')
            except BlygError as e:
                print(f'  ! resolve {cid}: {e}')
    print('done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
