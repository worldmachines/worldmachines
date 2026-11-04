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


def err(code, message, **details):
    out = {'code': code, 'message': message}
    if details:
        out['details'] = details
    return out


class FakeStudio:
    """Enough of Blygger Studio 0.51's owner API (private contract 5.2.0) for the sync, kept in memory.

    `catalog` maps a blyg base to the posts it serves; subscribing (or polling)
    imports them unless the post is marked `delayed`. `hopper_feeds` maps a
    member hopper's page URL to {'origin', 'feed', 'title', 'links'}: what a
    member's manifest offers as a hopper feed (§16.12), resolvable only while
    `settings['hopperFeeds']` is on.
    """

    PAGE = 100

    def __init__(self, catalog, hopper_feeds=None):
        self.catalog = catalog
        self.hopper_feeds = hopper_feeds or {}
        self.settings = {'postsPath': 'posts', 'hopperFeeds': True}
        self.subs = {}          # id → sub
        self.imported = []      # rows, newest observed first
        self.hoppers = {}       # id → hopper
        self.members = {}       # hopper id → [(sub, remote)]
        self.items = {}         # id → item
        self.calls = []
        self.generate_failures = []  # status codes to return on the next generate calls
        self.on_generate = None      # callable(item) run before each generate (to simulate a concurrent edit)
        self.withdrawn = set()
        self.status_override = None
        self.seq = 0

    def _id(self):
        self.seq += 1
        return rid(self.seq, prefix='z')

    def _row(self, sub, remote_id, kind, md, created, author, l0=False, source_url=None):
        return {
            'subscriptionId': sub['id'], 'subscriptionTitle': sub['title'],
            'remoteId': remote_id, 'kind': kind, 'withdrawn': False, 'l0': l0,
            'origin': sub['origin'], 'created': created, 'observedAt': '2026-10-31T00:00:00Z',
            'contentMd': md, 'contentHtml': '', 'author': {'name': author, 'url': None} if author else None,
            'page': None, 'sourceUrl': source_url, 'version': 1, 'readVersion': None, 'hoppers': [],
        }

    def _import(self, sub):
        have = {(r['subscriptionId'], r['remoteId']) for r in self.imported}
        sub['lastPollAt'] = '2026-10-31T00:00:00Z'
        if sub.get('hopperFeedUrl'):
            hf = next(v for v in self.hopper_feeds.values() if v['feed'] == sub['hopperFeedUrl'])
            for i, link in enumerate(hf['links']):
                key = f'l0-{abs(hash((sub["hopperFeedUrl"], link))) % 10 ** 12:012d}'
                if (sub['id'], key) not in have:
                    self.imported.insert(0, self._row(sub, key, 'fragment', f'[Entry {i}]({link})\n\nexcerpt',
                                                      '2026-10-30T00:00:00Z', 'Someone', l0=True, source_url=link))
            return
        for post in self.catalog.get(sub['origin'], []):
            if post.get('delayed') or (sub['id'], post['remoteId']) in have:
                continue
            md = f"# {post['title']}\n\nBody of {post['title']}."
            self.imported.insert(0, self._row(sub, post['remoteId'], post['kind'], md, post['created'], post['author']))

    def transport(self, method, url, headers, data):
        p = urllib.parse.urlsplit(url)
        path = p.path[len('/api'):]
        query = dict(urllib.parse.parse_qsl(p.query))
        body = json.loads(data) if data else None
        self.calls.append((method, path, body))
        if self.status_override:
            return self.status_override, {}, json.dumps(err('unauthorized', 'invalid token')).encode()
        assert headers['Authorization'] == 'Bearer tok'
        status, out = self.route(method, path, query, body)
        return status, {}, json.dumps(out).encode()

    def page(self, rows, query, max_limit=100):
        if 'offset' in query:
            return 400, err('invalid-input', 'offset paging was removed')
        start, lim = int(query.get('cursor') or 0), int(query.get('limit', self.PAGE))
        assert 1 <= lim <= max_limit, lim
        nxt = start + lim
        return 200, {'items': rows[start:nxt], 'page': {'limit': lim, 'nextCursor': str(nxt) if nxt < len(rows) else None}}

    def _item_write(self, item, body):
        if 'expectedRevision' not in body:
            return err('invalid-input', 'expectedRevision required')
        if body['expectedRevision'] != item['revision']:
            return err('revision-conflict', 'the item changed', itemId=item['id'], expectedRevision=body['expectedRevision'])
        return None

    def _subscribe(self, body):
        assert set(body) <= {'url', 'confirm', 'title', 'backfill', 'wholeBlyg'}, 'strict schema'
        url = body['url']
        hf = self.hopper_feeds.get(url)
        if hf and self.settings['hopperFeeds'] and not body.get('wholeBlyg'):
            if any(s.get('hopperFeedUrl') == hf['feed'] for s in self.subs.values()):
                return 409, err('conflict', f"already subscribed to {hf['title']}")
            title = f"{hf['title']} — Blyg at {hf['origin']}"
            if not body.get('confirm'):
                return 200, {'needsConfirm': True, 'kind': 'hopper', 'origin': hf['origin'], 'feedUrl': hf['feed'],
                             'title': title, 'hopper': {'title': hf['title'], 'page': url, 'feedUrl': hf['feed']},
                             'blygTitle': f"Blyg at {hf['origin']}"}
            sub = {'id': self._id(), 'kind': 'rss', 'origin': hf['origin'], 'feedUrl': hf['feed'], 'title': title,
                   'status': 'active', 'inBlogroll': False, 'flags': [], 'lastPollAt': None,
                   'hopperFeedUrl': hf['feed']}
            self.subs[sub['id']] = sub
            if body.get('backfill', True):
                self._import(sub)
            return 201, sub
        origin = hf['origin'] if hf else url  # with hopper feeds off, a hopper page resolves as its blyg
        if any(s['origin'] == origin and not s.get('hopperFeedUrl') for s in self.subs.values()):
            return 409, err('conflict', f'already subscribed to {origin}')
        if origin not in self.catalog:
            return 422, err('unprocessable', 'could not resolve this URL to a blyg or a feed')
        if not body.get('confirm'):
            return 200, {'needsConfirm': True, 'kind': 'blyg', 'origin': origin, 'title': f'Blyg at {origin}'}
        sub = {'id': self._id(), 'kind': 'blyg', 'origin': origin, 'feedUrl': origin + 'feed.xml',
               'title': f'Blyg at {origin}', 'status': 'active', 'inBlogroll': False, 'flags': [],
               'lastPollAt': None, 'hopperFeedUrl': None}
        self.subs[sub['id']] = sub
        if body.get('backfill', True):
            self._import(sub)
        return 201, sub

    def route(self, method, path, query, body):
        parts = path.strip('/').split('/')
        if path == '/settings' and method == 'GET':
            return 200, dict(self.settings)
        if path == '/subscriptions' and method == 'GET':
            return self.page(list(self.subs.values()), query)
        if path == '/subscriptions' and method == 'POST':
            return self._subscribe(body)
        if parts[0] == 'subscriptions' and len(parts) == 2 and method == 'PATCH' and parts[1] != 'poll':
            assert set(body) <= {'inBlogroll', 'title', 'paused'}, 'strict schema'
            sub = self.subs[parts[1]]
            sub.update(body)
            return 200, sub
        if path == '/subscriptions/poll':
            for s in self.subs.values():
                self._import(s)
            return 200, {'polling': len(self.subs)}
        if path == '/reading/imported':
            rows = [dict(r, withdrawn=r['remoteId'] in self.withdrawn) for r in self.imported]
            return self.page(rows, dict(query, limit=query.get('limit', 50)))
        if path == '/reading':
            rows = [{'key': f"{r['subscriptionId']}:{r['remoteId']}", 'source': 'imported', 'kind': r['kind'],
                     'imported': r} for r in self.imported if query.get('sub') in (None, r['subscriptionId'])]
            return self.page(rows, dict(query, limit=query.get('limit', 25)), max_limit=50)
        if path == '/hoppers' and method == 'GET':
            return self.page(list(self.hoppers.values()), query)
        if path == '/hoppers' and method == 'POST':
            slug = re.sub(r'[^a-z0-9]+', '-', body['name'].lower()).strip('-')
            h = {'id': self._id(), 'name': body['name'], 'slug': slug, 'public': False, 'slugFrozen': False,
                 'created': '2026-10-31T00:00:00Z', 'description': None}
            self.hoppers[h['id']] = h
            self.members[h['id']] = []
            return 201, h
        if parts[0] == 'hoppers' and len(parts) == 2:
            h = self.hoppers[parts[1]]
            if method == 'PATCH':
                assert set(body) <= {'name', 'public', 'description'}, 'strict schema'
                if 'name' in body:
                    h['name'] = body['name']
                    if not h['slugFrozen']:
                        h['slug'] = re.sub(r'[^a-z0-9]+', '-', body['name'].lower()).strip('-')
                if body.get('public'):
                    h['public'] = h['slugFrozen'] = True
                return 200, h
            return 200, {'hopper': h, 'total': len(self.members[h['id']]), 'sourceCount': 0}
        if parts[0] == 'hoppers' and len(parts) == 3 and parts[2] == 'memberships':
            held = {(r['subscriptionId'], r['remoteId']): r for r in self.imported}
            mem = [{'hopperId': parts[1], 'subscriptionId': s, 'remoteId': r, 'addedAt': '',
                    'item': held.get((s, r))} for s, r in reversed(self.members[parts[1]])]
            return self.page(mem, query)
        if parts[0] == 'hoppers' and parts[2] == 'items' and method == 'PUT':
            assert body is None, 'filing takes no body'
            key = (parts[3], parts[4])
            if key not in self.members[parts[1]]:
                self.members[parts[1]].append(key)
            return 200, {'ok': True}
        if path == '/items' and method == 'GET':
            rows = [i for i in self.items.values() if query.get('status') in (None, i['status'])]
            return self.page(rows, query)
        if path == '/items' and method == 'POST':
            assert set(body) <= {'kind', 'contentMd', 'mode', 'stubOf', 'provenance'}, 'strict schema'
            item = {'id': self._id(), 'revision': 1, 'kind': body['kind'], 'status': 'draft',
                    'contentMd': body['contentMd'], 'created': f'2026-10-31T00:00:{self.seq:02d}Z', 'version': 0,
                    'dirty': True}
            self.items[item['id']] = item
            return 201, item
        if parts[0] == 'items' and len(parts) == 2:
            item = self.items.get(parts[1])
            if not item:
                return 404, err('not-found', 'not found')
            if method == 'GET':
                return 200, item
            if method == 'PATCH':
                bad = self._item_write(item, body)
                if bad:
                    return 409 if bad['code'] == 'revision-conflict' else 400, bad
                item['contentMd'] = body['contentMd']
                item['revision'] += 1
                return 200, item
        if parts[0] == 'items' and parts[2] == 'generate':
            item = self.items[parts[1]]
            if self.on_generate:
                self.on_generate(item)
            bad = self._item_write(item, body)
            if bad:
                return 409 if bad['code'] == 'revision-conflict' else 400, bad
            return self.generate(item, body['scope'])
        if parts[0] == 'items' and parts[2] == 'publish':
            item = self.items[parts[1]]
            assert set(body) <= {'expectedRevision', 'note', 'noteGenerated', 'changeCategory'}, 'strict schema'
            bad = self._item_write(item, body)
            if bad:
                return 409 if bad['code'] == 'revision-conflict' else 400, bad
            if any('[=]' not in m.group(1) for m in blyg_sync.TK_SCOPE.finditer(item['contentMd'])):
                return 400, err('invalid-input', 'one or more TK scopes are not publish-ready')
            item['status'] = 'public'
            item['version'] += 1
            item['revision'] += 1
            return 200, {'ok': True, 'version': item['version'], 'revision': item['revision']}
        return 404, err('not-found', f'no route {method} {path}')

    def generate(self, item, scope):
        matches = list(blyg_sync.TK_SCOPE.finditer(item['contentMd']))
        if scope >= len(matches):
            return 400, err('invalid-input', 'unknown scope index')
        m = matches[scope]
        instr = m.group(1).split('[=]', 1)[0]
        known = {r['remoteId'] for r in self.imported}
        for sid in blyg_sync.SOURCE_REF.findall(instr):
            if sid not in known or sid in self.withdrawn:
                return 400, err('invalid-input', 'unresolvable source: source withdrawn by origin', id=sid,
                                reason='source withdrawn by origin')
        if self.generate_failures:
            code = self.generate_failures.pop(0)
            return code, err('rate-limit' if code == 429 else 'bad-gateway',
                             'daily AI budget spent' if code == 429 else 'provider error')
        text = f'Synthesis of scope {scope}.'
        md = item['contentMd']
        item['contentMd'] = md[:m.start()] + f'[TK]{instr}[=]{text}[/TK]' + md[m.end():]
        item['revision'] += 1
        return 200, {'text': text, 'model': '@cf/google/gemma-4-26b-a4b-it', 'contentMd': item['contentMd'],
                     'revision': item['revision']}

    # -- helpers for assertions
    def writes(self):
        return [c for c in self.calls if c[0] != 'GET']

    def filed(self):
        return [r for ms in self.members.values() for _, r in ms]

    def whole(self):
        return {s['origin']: s for s in self.subs.values() if not s.get('hopperFeedUrl')}

    def hopper_subs(self):
        return [s for s in self.subs.values() if s.get('hopperFeedUrl')]


def hopper_page(links):
    """A minimal Studio-style hopper page: one imported <article> per link."""
    arts = ''.join(
        f'<article class="fragment"><p>body</p><p class="provenance">from <a href="{u.split("t/")[0]}">x</a>'
        f' — <a href="{u}">source ↗</a></p></article>' for u in links)
    return f'<html><body><nav><a href="/t/{rid(999)}/">About</a></nav>{arts}</body></html>'


class Harness:
    def __init__(self, catalog, pages, hoppers, hopper_feeds=None):
        self.studio = FakeStudio(catalog, hopper_feeds)
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
        self.assertEqual(set(st.whole()), {VENKAT, PATRICK, ANEESH})
        self.assertEqual(st.hopper_subs(), [], 'no member offers its hopper as a feed here')
        self.assertIn('page scrape', h.out.getvalue())
        self.assertIn(('POST', '/subscriptions/poll', None), st.calls)
        (hopper,) = st.hoppers.values()
        self.assertEqual((hopper['slug'], hopper['name'], hopper['public']),
                         ('members', 'From World Machines members', True))
        # Oldest first; the nav-only "About" page is never filed.
        self.assertEqual(st.filed(), ['70qaqe3s0r0etzh9jgv4yfz6p6', '08e35za1360byb6p6e16jkx08q',
                                      '20nzf7p7kdhqjer2jfrfj29exf'])
        (digest,) = st.items.values()
        self.assertEqual(digest['status'], 'public')
        self.assertTrue(digest['contentMd'].startswith('# World Machines digest — 2026-10-31 (evening)'))
        self.assertIn('[=]Synthesis of scope 0.[/TK]', digest['contentMd'])
        self.assertIn('Patrick Atwater', digest['contentMd'])
        for c in st.writes():
            if c[1].startswith('/items/'):
                self.assertIn('expectedRevision', c[2], c)

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
        self.assertEqual([len(s[2]) for s in blyg_sync.tk_scopes(d1['contentMd'])], [6, 6])
        gens = [c for c in h.studio.calls if c[1].endswith('/generate')]
        self.assertEqual([c[2] for c in gens], [{'scope': 0, 'expectedRevision': 1}, {'scope': 1, 'expectedRevision': 2}])

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
        self.assertNotIn('![[70qaqe3s0r0etzh9jgv4yfz6p6]]', digest['contentMd'])
        self.assertNotIn('[[70qaqe3s0r0etzh9jgv4yfz6p6', digest['contentMd'])

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


class Blogroll(unittest.TestCase):
    """Approved hoppers' own blygs go in the WM blogroll; merely-linked ones do not."""

    def blogroll_patches(self, studio):
        return [c for c in studio.calls if c[0] == 'PATCH' and c[1].startswith('/subscriptions/')]

    def by_origin(self, studio):
        return studio.whole()

    def test_accepted_hopper_base_is_blogrolled_linked_blygs_are_not(self):
        h = history_harness()  # Venkat's hopper links Patrick's and Aneesh's posts
        _, result = h.run()
        subs = self.by_origin(h.studio)
        self.assertTrue(subs[VENKAT]['inBlogroll'])
        self.assertFalse(subs[PATRICK]['inBlogroll'])
        self.assertFalse(subs[ANEESH]['inBlogroll'])
        self.assertEqual(result['blogroll_added'], [VENKAT])
        (patch,) = self.blogroll_patches(h.studio)
        self.assertEqual(patch[2], {'inBlogroll': True})

    def test_idempotent_no_patch_when_already_true(self):
        h = history_harness()
        h.run()
        before = len(h.studio.calls)
        _, again = h.run()
        self.assertEqual(self.blogroll_patches(h.studio)[1:], [])
        self.assertEqual([c for c in h.studio.calls[before:] if c[0] != 'GET'], [])
        self.assertEqual(again['blogroll_added'], [])

    def test_existing_subscription_matched_by_normalized_base(self):
        h = Harness({VENKAT: []}, {HISTORY: hopper_page([])},
                    [{'canonical': HISTORY, 'base': 'HTTPS://VenkateshRao.COM/blyg', 'name': 'V'}])
        h.studio.subs['s1'] = {'id': 's1', 'kind': 'blyg', 'origin': VENKAT, 'title': 'V',
                               'status': 'active', 'inBlogroll': False}
        h.run(blogroll_only=True)
        self.assertNotIn('POST', [c[0] for c in h.studio.calls], 'no second subscription')
        self.assertEqual(self.blogroll_patches(h.studio), [('PATCH', '/subscriptions/s1', {'inBlogroll': True})])

    def test_already_true_is_left_alone_and_nothing_is_removed(self):
        h = Harness({VENKAT: []}, {HISTORY: hopper_page([])}, [{'url': HISTORY, 'name': 'V'}])
        h.studio.subs['s1'] = {'id': 's1', 'kind': 'blyg', 'origin': VENKAT, 'title': 'V',
                               'status': 'active', 'inBlogroll': True}
        h.studio.subs['s2'] = {'id': 's2', 'kind': 'blyg', 'origin': PATRICK, 'title': 'P',
                               'status': 'active', 'inBlogroll': True}  # no longer an approved hopper
        h.run()
        self.assertEqual(self.blogroll_patches(h.studio), [])
        self.assertTrue(h.studio.subs['s2']['inBlogroll'])

    def test_empty_hopper_still_subscribes_and_blogrolls_its_blyg(self):
        h = Harness({VENKAT: []}, {HISTORY: hopper_page([])}, [{'url': HISTORY, 'name': 'V'}])
        h.run()
        self.assertTrue(self.by_origin(h.studio)[VENKAT]['inBlogroll'])

    def test_own_blyg_is_never_blogrolled(self):
        site = 'https://blyg.worldmachines.org/'
        h = Harness({}, {site + 'h/x/': hopper_page([])}, [{'url': site + 'h/x/', 'name': 'WM'}])
        h.run(blogroll_only=True)
        self.assertEqual(h.studio.writes(), [])

    def test_dry_run_makes_no_writes(self):
        for preexisting in (False, True):
            h = history_harness()
            if preexisting:
                h.studio.subs['s1'] = {'id': 's1', 'kind': 'blyg', 'origin': VENKAT, 'title': 'V',
                                       'status': 'active', 'inBlogroll': False}
            for kw in ({}, {'blogroll_only': True}):
                sync, result = h.run(dry_run=True, **kw)
                self.assertEqual(h.studio.writes(), [])
                self.assertTrue(any(p.startswith(f'add {VENKAT} to the blogroll') for p in sync.plan), sync.plan)
                self.assertEqual(result['blogroll_added'], [VENKAT])

    def test_blogroll_only_does_no_scraping_filing_or_digest(self):
        h = history_harness()
        fetched = []
        orig = h.fetch
        h.fetch = lambda url: fetched.append(url) or orig(url)
        _, result = h.run(blogroll_only=True)
        self.assertEqual(fetched, [HOPPERS_URL, VENKAT + 'blyg.json'], 'only /api/hoppers and the manifest are read')
        st = h.studio
        self.assertEqual(set(self.by_origin(st)), {VENKAT})
        self.assertTrue(self.by_origin(st)[VENKAT]['inBlogroll'])
        self.assertEqual(st.hoppers, {}, 'no WM hopper created')
        self.assertEqual(st.filed(), [])
        self.assertEqual(st.items, {})
        self.assertNotIn(('POST', '/subscriptions/poll', None), st.calls)
        self.assertFalse(any(c[1].startswith(('/hoppers', '/items', '/reading')) for c in st.calls))
        self.assertEqual((result['filed'], result['digest']), ([], None))

    def test_main_blogroll_only_flag(self):
        h = history_harness()
        with mock.patch.dict(os.environ, {'BLYG_TOKEN': 'tok', 'BLYG_API_BASE': API, 'WM_HOPPERS_URL': HOPPERS_URL}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            blyg_sync.main(['--blogroll-only'], transport=h.studio.transport, fetch=h.fetch, sleep=lambda s: None)
        self.assertTrue(self.by_origin(h.studio)[VENKAT]['inBlogroll'])
        self.assertEqual(h.studio.items, {})
        self.assertEqual(h.studio.hoppers, {})
        self.assertIn('--blogroll-only', out.getvalue())


ANEESH_HISTORY = ANEESH + 'h/history/'
ANEESH_FEED = ANEESH + 'h/history/feed.xml'


def manifest(hoppers=None):
    m = {'blyg': '0.4', 'title': 'A blyg'}
    if hoppers is not None:
        m['hoppers'] = hoppers
    return json.dumps(m)


def feed_harness(offered=True, links=None, page_links=None):
    """Aneesh's hopper, offered as a hopper feed (Studio 0.50+) unless `offered` is False.

    Its entries link to Aneesh's own post, Venkat's post (as an item document)
    and a non-blyg page; the HTML page lists something else, so a test can
    tell which path supplied the wanted items.
    """
    a1, v1 = rid(101), rid(102)
    catalog = {
        ANEESH: [remote(ANEESH, a1, 'Hopper post', 'Aneesh Sathe', created='2026-10-05T00:00:00Z')],
        VENKAT: [remote(VENKAT, v1, 'Venkat post', 'Venkatesh Rao', created='2026-10-04T00:00:00Z'),
                 remote(VENKAT, rid(103), 'Scraped only', 'Venkatesh Rao', created='2026-10-03T00:00:00Z')],
    }
    links = links if links is not None else [f'{ANEESH}t/{a1}/', f'{VENKAT}items/{v1}.json', 'https://example.com/essay']
    entry = {'title': 'History', 'page': 'h/history/', 'feed': 'h/history/feed.xml'}
    pages = {
        ANEESH_HISTORY: hopper_page(page_links if page_links is not None else [f'{VENKAT}t/{rid(103)}/']),
        ANEESH + 'blyg.json': manifest([entry] if offered else None),
    }
    feeds = {ANEESH_HISTORY: {'origin': ANEESH, 'feed': ANEESH_FEED, 'title': 'History', 'links': links}}
    return Harness(catalog, pages, [{'url': ANEESH_HISTORY.rstrip('/'), 'name': 'Aneesh'}], feeds), a1, v1


class HopperFeeds(unittest.TestCase):
    def posts(self, studio):
        return [c for c in studio.calls if c[0] == 'POST' and c[1] == '/subscriptions']

    def test_hopper_subscription_created_via_proposal_then_confirm(self):
        h, a1, _ = feed_harness()
        _, result = h.run()
        st = h.studio
        (hsub,) = st.hopper_subs()
        self.assertEqual(hsub['hopperFeedUrl'], ANEESH_FEED)
        hopper_posts = [c[2] for c in self.posts(st) if c[2]['url'] == ANEESH_HISTORY]
        self.assertEqual(hopper_posts, [{'url': ANEESH_HISTORY, 'confirm': False},
                                        {'url': ANEESH_HISTORY, 'confirm': True, 'backfill': True}])
        # Its first run reads the page (the feed's entries arrive with the backfill) ...
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertIn('just created', h.out.getvalue())
        # ... the whole blyg is still subscribed and blogrolled; the hopper subscription never is.
        self.assertTrue(st.whole()[ANEESH]['inBlogroll'])
        self.assertFalse(hsub['inBlogroll'])
        self.assertEqual(st.whole()[ANEESH]['hopperFeedUrl'], None)

        # The next run follows the feed.
        _, again = h.run()
        self.assertEqual(again['routes'][ANEESH_HISTORY]['path'], 'feed')
        self.assertEqual(len(st.hopper_subs()), 1, 'not subscribed twice')
        self.assertIn(a1, st.filed())

    def test_hopper_feed_supplies_the_wanted_items(self):
        h, a1, v1 = feed_harness()
        h.run(digest=False)  # creates the hopper subscription; files what the page lists
        st = h.studio
        hid = next(iter(st.hoppers))
        st.members[hid] = []
        _, result = h.run()
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'feed')
        out = h.out.getvalue()
        self.assertIn('[hopper feed https://blyg.aneeshsathe.com/h/history/feed.xml]', out)
        self.assertIn("links to 'https://example.com/essay', not a blyg item; skipped", out)
        # The feed's entries (one by permalink, one by item document) are filed from the whole-blyg copies.
        self.assertEqual(sorted(st.filed()), sorted([v1, a1]))
        whole_ids = {s['id'] for s in st.whole().values()}
        self.assertTrue(all(sub in whole_ids for sub, _ in st.members[hid]), 'never an L0 hopper row')
        (digest,) = st.items.values()
        self.assertIn(f'![[{a1}]]', digest['contentMd'])
        self.assertNotIn('l0-', digest['contentMd'])
        self.assertEqual(digest['status'], 'public')

    def test_not_offered_falls_back_to_the_page(self):
        h, _, _ = feed_harness(offered=False)
        _, result = h.run()
        st = h.studio
        self.assertEqual(st.hopper_subs(), [])
        self.assertFalse([c for c in self.posts(st) if c[2]['url'] == ANEESH_HISTORY], 'the hopper page is never POSTed')
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertIn('does not offer it as a feed', h.out.getvalue())
        self.assertEqual(st.filed(), [rid(103)])

    def test_unreadable_manifest_falls_back(self):
        h, _, _ = feed_harness()
        del h.pages[ANEESH + 'blyg.json']
        _, result = h.run(digest=False)
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertEqual(h.studio.filed(), [rid(103)])

    def test_wm_setting_off_is_reported_and_falls_back(self):
        h, _, _ = feed_harness()
        h.studio.settings['hopperFeeds'] = False
        _, result = h.run(digest=False)
        st = h.studio
        self.assertEqual(st.hopper_subs(), [])
        self.assertFalse([c for c in self.posts(st) if c[2]['url'] == ANEESH_HISTORY], 'no proposal is sent')
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertIn('Settings → Network → hopper feeds', h.out.getvalue())
        self.assertEqual(st.filed(), [rid(103)])
        self.assertEqual(set(st.whole()), {ANEESH, VENKAT}, 'whole-blyg subscriptions by base, as before')
        self.assertNotIn(('PATCH', '/settings'), [c[:2] for c in st.calls], 'never flips the setting')

    def test_refusal_seen_in_the_proposal_when_the_setting_is_unreadable(self):
        h, _, _ = feed_harness()
        h.studio.settings['hopperFeeds'] = False
        route = h.studio.route
        h.studio.route = lambda m, p, q, b: (200, {'postsPath': 'posts'}) if p == '/settings' else route(m, p, q, b)
        _, result = h.run(digest=False)
        st = h.studio
        hopper_posts = [c[2] for c in self.posts(st) if c[2]['url'] == ANEESH_HISTORY]
        self.assertEqual(hopper_posts, [{'url': ANEESH_HISTORY, 'confirm': False}], 'proposal only, never confirmed')
        self.assertEqual(st.hopper_subs(), [])
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertIn('resolved https://blyg.aneeshsathe.com/h/history/ as blyg', h.out.getvalue())
        self.assertIn('Settings → Network → hopper feeds', h.out.getvalue())

    def test_dry_run_plans_the_hopper_subscription(self):
        h, _, _ = feed_harness()
        sync, result = h.run(dry_run=True)
        self.assertEqual(h.studio.writes(), [])
        self.assertTrue(any(p.startswith(f'subscribe to the hopper feed {ANEESH_FEED}') for p in sync.plan), sync.plan)
        h.studio.settings['hopperFeeds'] = False
        sync, _ = h.run(dry_run=True)
        self.assertFalse(any('hopper feed' in p for p in sync.plan))
        self.assertIn('Settings → Network → hopper feeds', h.out.getvalue())

    def test_paused_hopper_subscription_falls_back(self):
        h, _, _ = feed_harness()
        h.run(digest=False)
        (hsub,) = h.studio.hopper_subs()
        hsub.update(status='paused', flags=[{'type': 'hopper-unlisted', 'at': '2026-11-01T00:00:00Z'}])
        _, result = h.run(digest=False)
        self.assertEqual(result['routes'][ANEESH_HISTORY]['path'], 'scrape')
        self.assertIn('paused (hopper-unlisted)', h.out.getvalue())

    def test_blogroll_only_ensures_the_hopper_subscription(self):
        h, _, _ = feed_harness()
        _, result = h.run(blogroll_only=True)
        st = h.studio
        self.assertEqual([s['hopperFeedUrl'] for s in st.hopper_subs()], [ANEESH_FEED])
        self.assertTrue(st.whole()[ANEESH]['inBlogroll'])
        self.assertEqual((st.filed(), st.items, st.hoppers), ([], {}, {}))
        self.assertNotIn(ANEESH_HISTORY, [c for c in h.out.getvalue().splitlines() if 'item(s) [page scrape' in c])

    def test_parse_item_link(self):
        self.assertEqual(blyg_sync.parse_item_link(f'{VENKAT}items/{rid(1)}.json'), (VENKAT, None, rid(1)))
        self.assertEqual(blyg_sync.parse_item_link(f'{ANEESH}f/{rid(2)}/'), (ANEESH, 'f', rid(2)))
        self.assertIsNone(blyg_sync.parse_item_link('https://example.com/essay'))
        self.assertIsNone(blyg_sync.parse_item_link(None))


class Contract(unittest.TestCase):
    """Studio 0.51 private contract 5.2.0: revisions, cursors, errors."""

    def test_revision_conflict_rereads_and_retries_once(self):
        h = history_harness()
        bumped = []

        def concurrent_edit(item):
            if not bumped:  # someone saves the draft in Studio just before the first generate
                bumped.append(item['revision'])
                item['revision'] += 1

        h.studio.on_generate = concurrent_edit
        h.run()
        (digest,) = h.studio.items.values()
        self.assertEqual(digest['status'], 'public')
        gens = [c[2] for c in h.studio.calls if c[1].endswith('/generate')]
        self.assertEqual(gens[0]['expectedRevision'], 1)
        self.assertEqual(gens[1], {'scope': 0, 'expectedRevision': 2}, 'retried with the re-read revision')
        self.assertIn(('GET', f"/items/{digest['id']}", None), h.studio.calls)
        self.assertIn('re-reading and retrying once', h.out.getvalue())

    def test_second_revision_conflict_raises(self):
        h = history_harness()
        h.studio.on_generate = lambda item: item.__setitem__('revision', item['revision'] + 1)
        with self.assertRaises(blyg_sync.GenerationFailed) as cm:
            h.run()
        self.assertIn('revision-conflict', str(cm.exception))

    def test_cursor_pages_and_expired_cursor_restarts(self):
        rows = [{'id': f'i{n}'} for n in range(5)]
        calls = []

        def transport(method, url, headers, data):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            calls.append(query)
            if len(calls) == 2:
                return 409, {}, json.dumps({'code': 'cursor-expired', 'message': 'expired'}).encode()
            start = int(query.get('cursor') or 0)
            nxt = start + 2
            return 200, {}, json.dumps({'items': rows[start:nxt], 'page': {
                'limit': 2, 'nextCursor': str(nxt) if nxt < len(rows) else None}}).encode()

        api = blyg_sync.BlygApi(API, 'tok', transport=transport, write_interval=0, sleep=lambda s: None)
        with contextlib.redirect_stdout(io.StringIO()):
            got = [r['id'] for r in api.paged('/items', limit=2, status='draft')]
        self.assertEqual(got, ['i0', 'i1', 'i2', 'i3', 'i4'], 'restarted, no duplicates')
        self.assertNotIn('offset', ''.join(json.dumps(c) for c in calls))
        self.assertEqual(calls[0], {'limit': '2', 'status': 'draft'})
        self.assertEqual(calls[2], {'limit': '2', 'status': 'draft'}, 'restart drops the cursor')

    def test_error_shape_in_messages(self):
        e = blyg_sync.BlygError(409, 'POST', '/x', {'code': 'conflict', 'message': 'already subscribed',
                                                     'details': {'id': 'a'}})
        self.assertEqual((e.code, e.message, e.details), ('conflict', 'already subscribed', {'id': 'a'}))
        self.assertIn('HTTP 409: conflict: already subscribed', str(e))


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
