"""Tests for scripts/blyg_sync.py (member hoppers → WM blyg → TK digest).

Run from website/:  python -m unittest discover -s tests
Network is never touched: the Studio API is an in-memory fake behind the
script's transport seam, and public pages come from a dict.
"""
import contextlib
import io
import json
import os
import re
import sys
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
sys.path.insert(0, str(SCRIPTS))

import blyg_sync  # noqa: E402

API = 'https://blyg.worldmachines.org/api'
HOPPERS_URL = 'https://worldmachines.org/api/hoppers'
VENKAT = 'https://venkateshrao.com/blyg/'
PATRICK = 'https://pioneering-spirit-blyg.patrickatwater.workers.dev/'
ANEESH = 'https://blyg.aneeshsathe.com/'
HISTORY = 'https://venkateshrao.com/blyg/h/history/'
ALPHA = blyg_sync.ID_CHARS


def rid(n, prefix='0'):
    """A valid 26-char id, distinct per n."""
    s = ''
    while True:
        s = ALPHA[n % 32] + s
        n //= 32
        if not n:
            break
    return (prefix + s).rjust(26, 'a')


def remote(origin, remote_id, title, author, kind='thread', created='2026-10-01T00:00:00Z', **kw):
    return dict(origin=origin, remoteId=remote_id, kind=kind, title=title, author=author, created=created, **kw)


class FakeStudio:
    """Enough of Blygger Studio v0.49.1's owner API for the sync, kept in memory.

    `catalog` maps a blyg base to the posts it serves; subscribing (or polling)
    imports them unless the post is marked `delayed`.
    """

    def __init__(self, catalog):
        self.catalog = catalog
        self.subs = {}          # id → sub
        self.imported = []      # rows, newest observed first
        self.hoppers = {}       # id → hopper
        self.members = {}       # hopper id → [(sub, remote)]
        self.items = {}         # id → item
        self.calls = []
        self.generate_failures = []  # status codes to return on the next generate calls
        self.withdrawn = set()
        self.status_override = None
        self.seq = 0

    def _id(self):
        self.seq += 1
        return rid(self.seq, prefix='z')

    def _import(self, sub):
        have = {(r['subscriptionId'], r['remoteId']) for r in self.imported}
        for post in self.catalog.get(sub['origin'], []):
            if post.get('delayed') or (sub['id'], post['remoteId']) in have:
                continue
            md = f"# {post['title']}\n\nBody of {post['title']}."
            self.imported.insert(0, {
                'subscriptionId': sub['id'], 'subscriptionTitle': sub['title'],
                'remoteId': post['remoteId'], 'kind': post['kind'], 'withdrawn': False, 'l0': False,
                'origin': sub['origin'], 'created': post['created'], 'observedAt': '2026-10-31T00:00:00Z',
                'contentMd': md, 'contentHtml': '', 'author': {'name': post['author'], 'url': None},
                'page': None, 'sourceUrl': None, 'version': 1, 'hoppers': [],
            })

    def transport(self, method, url, headers, data):
        p = urllib.parse.urlsplit(url)
        path = p.path[len('/api'):]
        query = dict(urllib.parse.parse_qsl(p.query))
        body = json.loads(data) if data else None
        self.calls.append((method, path, body))
        if self.status_override:
            return self.status_override, {}, json.dumps({'error': 'invalid token'}).encode()
        assert headers['Authorization'] == 'Bearer tok'
        status, out = self.route(method, path, query, body)
        return status, {}, json.dumps(out).encode()

    def page(self, rows, query):
        off, lim = int(query.get('offset', 0)), int(query.get('limit', 100))
        return {'items': rows[off:off + lim], 'total': len(rows), 'offset': off, 'limit': lim}

    def route(self, method, path, query, body):
        parts = path.strip('/').split('/')
        if path == '/subscriptions' and method == 'GET':
            return 200, self.page(list(self.subs.values()), query)
        if path == '/subscriptions' and method == 'POST':
            origin = body['url']
            if any(s['origin'] == origin for s in self.subs.values()):
                return 409, {'error': f'already subscribed to {origin}'}
            if origin not in self.catalog:
                return 422, {'error': 'could not resolve this URL to a blyg or a feed'}
            sub = {'id': self._id(), 'kind': 'blyg', 'origin': origin, 'feed_url': origin + 'feed.xml',
                   'title': f'Blyg at {origin}', 'status': 'active'}
            self.subs[sub['id']] = sub
            if body.get('backfill', True):
                self._import(sub)
            return 201, sub
        if path == '/subscriptions/poll':
            for s in self.subs.values():
                self._import(s)
            return 200, {'polling': len(self.subs)}
        if path == '/reading/imported':
            rows = [dict(r, withdrawn=r['remoteId'] in self.withdrawn) for r in self.imported]
            start = int(query.get('cursor') or 0)
            lim = int(query.get('limit', 50))
            nxt = start + lim
            return 200, {'items': rows[start:nxt], 'next': str(nxt) if nxt < len(rows) else None, 'limit': lim}
        if path == '/hoppers' and method == 'GET':
            return 200, self.page(list(self.hoppers.values()), query)
        if path == '/hoppers' and method == 'POST':
            slug = re.sub(r'[^a-z0-9]+', '-', body['name'].lower()).strip('-')
            h = {'id': self._id(), 'name': body['name'], 'slug': slug, 'public': False, 'slug_frozen': False}
            self.hoppers[h['id']] = h
            self.members[h['id']] = []
            return 201, h
        if parts[0] == 'hoppers' and len(parts) == 2:
            h = self.hoppers[parts[1]]
            if method == 'PATCH':
                if 'name' in body:
                    h['name'] = body['name']
                    if not h['slug_frozen']:
                        h['slug'] = re.sub(r'[^a-z0-9]+', '-', body['name'].lower()).strip('-')
                if body.get('public'):
                    h['public'] = h['slug_frozen'] = True
                return 200, h
            mem = [{'hopper_id': h['id'], 'subscription_id': s, 'remote_id': r, 'added_at': ''}
                   for s, r in self.members[h['id']]]
            return 200, {'hopper': h, 'memberships': mem, 'items': [], 'total': len(mem), 'source_count': 0}
        if parts[0] == 'hoppers' and parts[2] == 'items' and method == 'PUT':
            assert body is None, 'filing takes no body'
            key = (parts[3], parts[4])
            if key not in self.members[parts[1]]:
                self.members[parts[1]].append(key)
            return 200, {'ok': True}
        if path == '/items' and method == 'GET':
            return 200, self.page(list(self.items.values()), query)
        if path == '/items' and method == 'POST':
            item = {'id': self._id(), 'kind': body['kind'], 'status': 'draft', 'content_md': body['content_md'],
                    'created': f'2026-10-31T00:00:{self.seq:02d}Z', 'version': 0}
            self.items[item['id']] = item
            return 201, item
        if parts[0] == 'items' and len(parts) == 2 and method == 'PATCH':
            self.items[parts[1]]['content_md'] = body['content_md']
            return 200, self.items[parts[1]]
        if parts[0] == 'items' and parts[2] == 'generate':
            return self.generate(self.items[parts[1]], body['scope'])
        if parts[0] == 'items' and parts[2] == 'publish':
            item = self.items[parts[1]]
            if any('[=]' not in m.group(1) for m in blyg_sync.TK_SCOPE.finditer(item['content_md'])):
                return 400, {'error': 'TK scopes are not publish-ready'}
            item['status'] = 'public'
            item['version'] += 1
            return 200, {'ok': True, 'version': item['version']}
        return 404, {'error': f'no route {method} {path}'}

    def generate(self, item, scope):
        matches = list(blyg_sync.TK_SCOPE.finditer(item['content_md']))
        if scope >= len(matches):
            return 400, {'error': 'unknown scope index'}
        m = matches[scope]
        instr = m.group(1).split('[=]', 1)[0]
        known = {r['remoteId'] for r in self.imported}
        for sid in blyg_sync.SOURCE_REF.findall(instr):
            if sid not in known or sid in self.withdrawn:
                return 400, {'error': 'unresolvable source: source withdrawn by origin', 'id': sid,
                             'reason': 'source withdrawn by origin'}
        if self.generate_failures:
            code = self.generate_failures.pop(0)
            return code, {'error': 'daily AI budget spent' if code == 429 else 'provider error'}
        text = f'Synthesis of scope {scope}.'
        md = item['content_md']
        item['content_md'] = md[:m.start()] + f'[TK]{instr}[=]{text}[/TK]' + md[m.end():]
        return 200, {'text': text, 'model': '@cf/google/gemma-4-26b-a4b-it', 'content_md': item['content_md']}

    # -- helpers for assertions
    def writes(self):
        return [c for c in self.calls if c[0] != 'GET']

    def filed(self):
        return [r for ms in self.members.values() for _, r in ms]


def hopper_page(links):
    """A minimal Studio-style hopper page: one imported <article> per link."""
    arts = ''.join(
        f'<article class="fragment"><p>body</p><p class="provenance">from <a href="{u.split("t/")[0]}">x</a>'
        f' — <a href="{u}">source ↗</a></p></article>' for u in links)
    return f'<html><body><nav><a href="/t/{rid(999)}/">About</a></nav>{arts}</body></html>'


class Harness:
    def __init__(self, catalog, pages, hoppers):
        self.studio = FakeStudio(catalog)
        self.pages = dict(pages)
        self.pages[HOPPERS_URL] = json.dumps({'hoppers': hoppers})
        self.out = io.StringIO()

    def fetch(self, url):
        if url not in self.pages:
            raise RuntimeError(f'GET {url} → HTTP 404')
        return self.pages[url]

    def run(self, dry_run=False, now=datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc), **kw):
        api = blyg_sync.BlygApi(API, 'tok', transport=self.studio.transport, dry_run=dry_run,
                                write_interval=0, sleep=lambda s: None)
        sync = blyg_sync.Sync(api, fetch=self.fetch, hoppers_url=HOPPERS_URL, dry_run=dry_run,
                              poll_wait=0, sleep=lambda s: None, now=now, **kw)
        with contextlib.redirect_stdout(self.out):
            result = sync.run()
        return sync, result


def history_harness():
    html = (FIXTURES / 'hopper_venkat_history.html').read_text(encoding='utf-8')
    catalog = {
        VENKAT: [remote(VENKAT, '20nzf7p7kdhqjer2jfrfj29exf', 'Cognitive mercantilism', 'Venkatesh Rao',
                        created='2026-10-03T00:00:00Z'),
                 remote(VENKAT, '6gd003w2dffqce5b53ehvn7kw2', 'About', 'Venkatesh Rao')],
        PATRICK: [remote(PATRICK, '70qaqe3s0r0etzh9jgv4yfz6p6', 'On definitions', 'Patrick Atwater',
                         created='2026-10-01T00:00:00Z')],
        ANEESH: [remote(ANEESH, '08e35za1360byb6p6e16jkx08q', 'Crash course capitalism', 'Aneesh Sathe',
                        created='2026-10-02T00:00:00Z')],
    }
    # Today's /api/hoppers shape: no canonical/base, url without the trailing slash.
    hoppers = [{'url': HISTORY.rstrip('/'), 'name': 'Venkat', 'handle': 'vgr', 'title': 'History'}]
    return Harness(catalog, {HISTORY: html}, hoppers)


# ---------------------------------------------------------------- unit tests

class PermalinkExtraction(unittest.TestCase):
    def test_real_hopper_page(self):
        html = (FIXTURES / 'hopper_venkat_history.html').read_text(encoding='utf-8')
        items = blyg_sync.extract_items(html, HISTORY)
        self.assertEqual(items, [
            (VENKAT, 't', '20nzf7p7kdhqjer2jfrfj29exf'),   # own thread card (relative link)
            (PATRICK, 't', '70qaqe3s0r0etzh9jgv4yfz6p6'),  # imported from another blyg
            (ANEESH, 't', '08e35za1360byb6p6e16jkx08q'),   # imported; its quotes are not members
        ])
        ids = {i for _, _, i in items}
        self.assertNotIn('6gd003w2dffqce5b53ehvn7kw2', ids, 'the nav "About" page is not a member')

    def test_version_links_are_not_permalinks(self):
        self.assertIsNone(blyg_sync.parse_permalink(VENKAT + 't/20nzf7p7kdhqjer2jfrfj29exf/v4/'))
        self.assertEqual(blyg_sync.parse_permalink('HTTPS://Blyg.AneeshSathe.com/f/08e35za1360byb6p6e16jkx08q'),
                         (ANEESH, 'f', '08e35za1360byb6p6e16jkx08q'))
        self.assertIsNone(blyg_sync.parse_permalink(VENKAT + 'h/history/'))

    def test_fallback_without_articles_skips_nav(self):
        own = rid(1)
        html = (f'<nav><a href="/blyg/t/{rid(2)}/">About</a></nav>'
                f'<a href="/blyg/t/{own}/">post</a><a href="/blyg/t/{own}/v2/">v2</a>')
        self.assertEqual(blyg_sync.extract_items(html, HISTORY), [(VENKAT, 't', own)])

    def test_wm_hoppers_both_shapes(self):
        today = {'hoppers': [{'url': 'https://venkateshrao.com/blyg/h/history', 'name': 'V'}]}
        planned = {'hoppers': [{'canonical': 'https://venkateshrao.com/blyg/h/history/',
                                'base': 'https://venkateshrao.com/blyg', 'name': 'V'}]}
        for payload in (today, planned):
            (h,) = blyg_sync.parse_wm_hoppers(payload)
            self.assertEqual(h['canonical'], HISTORY)
            self.assertEqual(h['base'], VENKAT)

    def test_site_from_api_base(self):
        self.assertEqual(blyg_sync.site_from_api_base(API), 'https://blyg.worldmachines.org/')
        self.assertEqual(blyg_sync.site_from_api_base('https://x.org/blyg/api/'), 'https://x.org/blyg/')


class DigestBuilding(unittest.TestCase):
    def rows(self, n):
        return [{'remoteId': rid(i), 'subscriptionId': 's', 'origin': VENKAT, 'kind': 'thread',
                 'contentMd': f'# Post [{i}]\n\nbody', 'author': {'name': f'Author {i % 3}'}} for i in range(n)]

    def test_scopes_are_capped_and_split(self):
        md = blyg_sync.build_digest(self.rows(14), datetime(2026, 10, 31, 6, tzinfo=timezone.utc),
                                    'https://blyg.worldmachines.org/h/members/', max_sources=6)
        scopes = blyg_sync.tk_scopes(md)
        self.assertEqual([len(s[2]) for s in scopes], [6, 6, 2])
        self.assertTrue(md.startswith('# World Machines digest — 2026-10-31 (morning)\n'))
        self.assertIn('part 1 of 3', md)
        self.assertIn(f'- [[{rid(0)} | Post 0]] — Author 0', md, 'list links use [[id | label]], brackets stripped')

    def test_drop_source(self):
        a, b = rid(1), rid(2)
        md = f'x\n\n[TK]do ![[{a}]] ![[{b}]][/TK]\n\n[TK]solo ![[{b}]][/TK]\n\n- [[{b} | Bee]] — B\n'
        out = blyg_sync.drop_source(md, b)
        self.assertEqual(out, f'x\n\n[TK]do ![[{a}]][/TK]\n\n\n\n- Bee — B\n')


# ---------------------------------------------------------------- end to end, mocked

class EndToEnd(unittest.TestCase):
    def test_first_run_then_idempotent(self):
        h = history_harness()
        _, result = h.run()
        st = h.studio
        self.assertEqual({s['origin'] for s in st.subs.values()}, {VENKAT, PATRICK, ANEESH})
        self.assertIn(('POST', '/subscriptions/poll', None), st.calls)
        (hopper,) = st.hoppers.values()
        self.assertEqual((hopper['slug'], hopper['name'], hopper['public']),
                         ('members', 'From World Machines members', True))
        # Oldest first; the nav-only "About" page is never filed.
        self.assertEqual(st.filed(), ['70qaqe3s0r0etzh9jgv4yfz6p6', '08e35za1360byb6p6e16jkx08q',
                                      '20nzf7p7kdhqjer2jfrfj29exf'])
        (digest,) = st.items.values()
        self.assertEqual(digest['status'], 'public')
        self.assertTrue(digest['content_md'].startswith('# World Machines digest — 2026-10-31 (evening)'))
        self.assertIn('[=]Synthesis of scope 0.[/TK]', digest['content_md'])
        self.assertIn('Patrick Atwater', digest['content_md'])

        before = len(st.writes())
        _, again = h.run()
        self.assertEqual(st.writes()[before:], [], 'a second run writes nothing')
        self.assertEqual(again['filed'], [])
        self.assertEqual(len(st.items), 1, 'no second digest')

    def test_items_not_yet_imported_wait(self):
        h = history_harness()
        h.studio.catalog[ANEESH][0]['delayed'] = True
        _, result = h.run()
        self.assertNotIn('08e35za1360byb6p6e16jkx08q', h.studio.filed())
        self.assertEqual([w['id'] for w in result['missing']], ['08e35za1360byb6p6e16jkx08q'])
        self.assertIn('not imported yet', h.out.getvalue())

        h.studio.catalog[ANEESH][0]['delayed'] = False
        h.studio.route('POST', '/subscriptions/poll', {}, None)  # the 15-minute cron
        _, result = h.run()
        self.assertEqual([r['remoteId'] for r in result['filed']], ['08e35za1360byb6p6e16jkx08q'])
        self.assertEqual(len(h.studio.items), 2)
        self.assertTrue(all(i['status'] == 'public' for i in h.studio.items.values()))

    def test_skips_own_blyg_items(self):
        site = 'https://blyg.worldmachines.org/'
        h = Harness({}, {HISTORY: hopper_page([f'{site}t/{rid(5)}/'])},
                    [{'url': HISTORY.rstrip('/'), 'name': 'V'}])
        _, result = h.run()
        self.assertEqual(h.studio.subs, {})
        self.assertEqual(result['filed'], [])

    def test_source_cap_leaves_leftovers_for_next_run(self):
        posts = [remote(VENKAT, rid(i), f'Post {i}', 'Venkatesh Rao', created=f'2026-10-{i + 1:02d}T00:00:00Z')
                 for i in range(14)]
        page = hopper_page([f'{VENKAT}t/{p["remoteId"]}/' for p in posts])
        h = Harness({VENKAT: posts}, {HISTORY: page}, [{'url': HISTORY.rstrip('/'), 'name': 'V'}])
        _, first = h.run(max_sources=6, max_scopes=2)
        self.assertEqual([r['remoteId'] for r in first['filed']], [rid(i) for i in range(12)])
        (d1,) = h.studio.items.values()
        self.assertEqual([len(s[2]) for s in blyg_sync.tk_scopes(d1['content_md'])], [6, 6])
        gens = [c for c in h.studio.calls if c[1].endswith('/generate')]
        self.assertEqual([c[2] for c in gens], [{'scope': 0}, {'scope': 1}])

        _, second = h.run(max_sources=6, max_scopes=2)
        self.assertEqual([r['remoteId'] for r in second['filed']], [rid(12), rid(13)])
        self.assertEqual(len(h.studio.items), 2)

    def test_resume_unfinished_draft(self):
        h = history_harness()
        h.studio.generate_failures = [429]
        with self.assertRaises(blyg_sync.GenerationFailed) as cm:
            h.run()
        self.assertIn('AI budget', str(cm.exception))
        (draft,) = h.studio.items.values()
        self.assertEqual(draft['status'], 'draft')
        self.assertEqual(len(h.studio.filed()), 3, 'filing happened before generation')

        _, result = h.run(now=datetime(2026, 11, 1, 6, tzinfo=timezone.utc))
        self.assertEqual(len(h.studio.items), 1, 'resumed, not duplicated')
        self.assertEqual(draft['status'], 'public')
        self.assertEqual(result['filed'], [])
        self.assertIn('Resuming unfinished digest', h.out.getvalue())

    def test_resume_files_what_the_draft_names(self):
        """A run that died after creating the draft but before filing still files everything."""
        h = history_harness()
        h.run(digest=False)  # subscribe + file all three
        st = h.studio
        hid = next(iter(st.hoppers))
        st.members[hid] = []
        st.generate_failures = [502]
        with self.assertRaises(blyg_sync.GenerationFailed) as cm:
            h.run()
        self.assertIn('provider', str(cm.exception))
        st.members[hid] = []  # pretend the filing never happened
        h.run()
        self.assertEqual(len(st.filed()), 3)
        self.assertEqual([i['status'] for i in st.items.values()], ['public'])

    def test_withdrawn_source_is_dropped_not_stuck(self):
        h = history_harness()
        h.studio.withdrawn.add('70qaqe3s0r0etzh9jgv4yfz6p6')
        h.run()
        (digest,) = h.studio.items.values()
        self.assertEqual(digest['status'], 'public')
        self.assertNotIn('![[70qaqe3s0r0etzh9jgv4yfz6p6]]', digest['content_md'])
        self.assertNotIn('[[70qaqe3s0r0etzh9jgv4yfz6p6', digest['content_md'])

    def test_no_digest_flag(self):
        h = history_harness()
        _, result = h.run(digest=False)
        self.assertEqual(len(result['filed']), 3)
        self.assertEqual(h.studio.items, {})

    def test_dry_run_is_read_only(self):
        h = history_harness()
        sync, result = h.run(dry_run=True)
        self.assertEqual(h.studio.writes(), [], 'dry run sends only GETs')
        self.assertTrue(any(p.startswith('subscribe to') for p in sync.plan))
        self.assertTrue(any(p.startswith('create hopper') for p in sync.plan))
        # Nothing is imported until we subscribe, so nothing is filed in the plan.
        self.assertEqual(result['filed'], [])

    def test_dry_run_with_existing_state_prints_digest(self):
        h = history_harness()
        h.run(digest=False)
        hid = next(iter(h.studio.hoppers))
        h.studio.members[hid] = []
        before = len(h.studio.writes())
        sync, result = h.run(dry_run=True)
        self.assertEqual(h.studio.writes()[before:], [])
        self.assertEqual(len(result['filed']), 3)
        self.assertIn('[TK]', result['digest'])
        self.assertIn('----- digest draft -----', h.out.getvalue())
        self.assertTrue(any(p.startswith('create the digest draft') for p in sync.plan))


class Auth(unittest.TestCase):
    def test_401_is_loud(self):
        h = history_harness()
        h.studio.status_override = 401
        with self.assertRaises(blyg_sync.AuthError) as cm:
            h.run()
        msg = str(cm.exception)
        self.assertIn('HTTP 401', msg)
        self.assertIn('30 days', msg)
        self.assertIn('Client access', msg)
        self.assertIn('owner:read owner:manage owner:draft owner:publish', msg)
        self.assertIn('BLYG_TOKEN', msg)

    def test_main_exits_with_the_message(self):
        h = history_harness()
        h.studio.status_override = 403
        with mock.patch.dict(os.environ, {'BLYG_TOKEN': 'tok', 'BLYG_API_BASE': API}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                blyg_sync.main(['--poll-wait', '0'], transport=h.studio.transport, fetch=h.fetch,
                               sleep=lambda s: None)
        self.assertIn('Mint a new one', str(cm.exception.code))
        self.assertIn('::error::BLYG_TOKEN refused (HTTP 403)', err.getvalue())

    def test_missing_token(self):
        with mock.patch.dict(os.environ, {'BLYG_TOKEN': ''}):
            with self.assertRaises(SystemExit) as cm:
                blyg_sync.main([])
        self.assertIn('BLYG_TOKEN is not set', str(cm.exception.code))


if __name__ == '__main__':
    unittest.main()
