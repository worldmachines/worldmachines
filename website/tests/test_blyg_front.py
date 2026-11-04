"""Tests for scripts/blyg_front.py (the blyg's AI-curated front page).

Run from website/:  python -m unittest discover -s tests
Network is never touched: the Studio API and Workers AI are in-memory fakes
behind the script's transport seams, and the corpus is a few synthetic notes.
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import blyg_front as F  # noqa: E402
import corpus as C  # noqa: E402  (tools/blyg-import, put on sys.path by blyg_front)

API = 'https://blyg.example/api'
SITE = 'https://blyg.example/'
NOW = datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)
ALPHA = '0123456789abcdefghjkmnpqrstvwxyz'


def rid(n, prefix='n'):
    s = ''
    while True:
        s = ALPHA[n % 32] + s
        n //= 32
        if not n:
            break
    return (prefix + s).rjust(26, 'a')


def prose(topic, n=30):
    return ' '.join(f'The {topic} shaped how the modern state read its subjects in case {i}.' for i in range(n))


def note(path, title, body, **front):
    fm = ''.join(f'{k}: "{v}"\n' for k, v in front.items())
    raw = (f'---\n{fm}---\n' if fm else '') + f'# {title}\n\n{body}\n'
    return C.parse_note(path, raw)


def make_corpus():
    notes = [
        note('raw-notes/commons/glossary/legibility.md', 'Legibility', prose('census') + ' See [[modernity-machine]].',
             summary='Readable by a system that can act on what it reads.'),
        note('raw-notes/commons/glossary/README.md', 'The glossary', prose('glossary')),
        note('raw-notes/aneesh/concepts/modernity-machine.md', 'Modernity Machine',
             prose('modernity machine') + ' Built on [[legibility]].'),
        note('raw-notes/aneesh/concepts/stub.md', 'Stub', 'Too short to feature.'),
        note('raw-notes/aneesh/index.md', 'Aneesh index', prose('index') + ' [[modernity-machine]] [[legibility]]'),
        note('raw-notes/sean/reoccupation.md', 'Reoccupation', prose('vacant position') + ' [[legibility]]'),
        note('raw-notes/commons/synthesis/bourgeois.md', 'Bourgeois inwardness', prose('diary') + ' [[legibility]]'),
        note('raw-notes/commons/summaries/more-utopia.md', 'Utopia (Thomas More, 1516)', prose('Utopian gold')),
        note('raw-notes/commons/reading/more-utopia/more-utopia-01.md', 'Hythloday', prose('counsel')),
        note('raw-notes/commons/reading/more-utopia/more-utopia-02.md', 'Gold chamber pots', prose('chamber pot')),
        note('raw-notes/commons/reading/more-utopia/more-utopia-03.md', 'Slaves in Utopia', prose('bondage')),
        note('raw-notes/commons/reading/mann-1493/mann-1493-01.md', 'Shiploads of silver', prose('silver')),
        note('raw-notes/commons/entities/adam-smith.md', 'Adam Smith', prose('invisible hand')),
        note('raw-notes/commons/contributions/essay/essay-p01.md', 'An essay (part 1 of 2)', prose('essay')),
        note('raw-notes/florian/drainage.md', 'Hilarious drainage', prose('drain')),
        note('raw-notes/florian/unpublished.md', 'Never imported', prose('ghost')),
        note('wiki/README.md', 'Wiki', prose('wiki')),
    ]
    state = {}
    for i, n in enumerate(notes):
        if n.path != 'raw-notes/florian/unpublished.md':
            state[n.path] = {'id': rid(i), 'published_version': 1}
    authors = C.Authors(authors={'aneesh': {'name': 'Aneesh Sathe', 'blyg': None},
                                 'sean': {'name': 'Sean Stevenson', 'blyg': None},
                                 'florian': {'name': 'Florian Lohse', 'blyg': None}}, handles={})
    return F.Corpus(notes=notes, state=state, authors=authors, config_path=None)


# ---------------------------------------------------------------- fakes

def err(code, message, **details):
    out = {'code': code, 'message': message}
    if details:
        out['details'] = details
    return out


class FakeStudio:
    """Enough of Blygger Studio 0.51's owner API (private contract 5.2.0) for the front page."""

    def __init__(self):
        self.items = {}
        self.calls = []
        self.hoppers = []
        self.memberships = {}   # hopper id → [membership rows with `item`], newest first
        self.subs = []
        self.generate_status = 200
        self.seq = 0

    def transport(self, method, url, headers, data):
        p = urllib.parse.urlsplit(url)
        path = p.path[len('/api'):]
        query = dict(urllib.parse.parse_qsl(p.query))
        body = json.loads(data) if data else None
        self.calls.append((method, path, body))
        status, out = self.route(method, path, query, body)
        return status, {}, json.dumps(out).encode()

    def writes(self, kind=None):
        return [c for c in self.calls if c[0] != 'GET' and (kind is None or c[1].endswith(kind))]

    @staticmethod
    def page(rows, query):
        if 'offset' in query:
            return 400, err('invalid-input', 'offset paging was removed')
        start, lim = int(query.get('cursor') or 0), int(query.get('limit', 100))
        nxt = start + lim
        return 200, {'items': rows[start:nxt], 'page': {'limit': lim, 'nextCursor': str(nxt) if nxt < len(rows) else None}}

    @staticmethod
    def conflict(item, body):
        if body is None or 'expectedRevision' not in body:
            return 400, err('invalid-input', 'expectedRevision required')
        if body['expectedRevision'] != item['revision']:
            return 409, err('revision-conflict', 'stale', itemId=item['id'], expectedRevision=body['expectedRevision'])
        return None

    def route(self, method, path, query, body):
        parts = path.strip('/').split('/')
        if path == '/settings':
            assert method == 'GET', 'the front page never changes settings'
            return 200, {'postsPath': 'posts', 'frontPage': None, 'hopperFeeds': False}
        if path == '/items' and method == 'GET':
            rows = sorted((i for i in self.items.values() if query.get('status') in (None, i['status'])),
                          key=lambda i: i['updated'], reverse=True)
            return self.page(rows, query)
        if path == '/items' and method == 'POST':
            assert set(body) <= {'kind', 'contentMd', 'mode'}, 'strict schema'
            self.seq += 1
            item = {'id': rid(self.seq, 'f'), 'revision': 1, 'kind': 'thread', 'status': 'draft', 'version': 0,
                    'contentMd': body['contentMd'], 'dirty': True, 'updated': f'2026-11-02T00:00:{self.seq:02d}Z'}
            self.items[item['id']] = item
            return 201, item
        if parts[0] == 'items' and len(parts) == 2:
            item = self.items.get(parts[1])
            if not item:
                return 404, err('not-found', 'not found')
            if method == 'PATCH':
                bad = self.conflict(item, body)
                if bad:
                    return bad
                item['contentMd'] = body['contentMd']
                item['dirty'] = True
                item['revision'] += 1
            return 200, item
        if parts[0] == 'items' and parts[2] == 'generate':
            item = self.items[parts[1]]
            bad = self.conflict(item, body)
            if bad:
                return bad
            if self.generate_status != 200:
                return self.generate_status, err('rate-limit', 'daily AI call budget exceeded')
            md = item['contentMd']
            m = next(x for x in re.finditer(r'\[TK\](.*?)\[/TK\]', md, re.S) if not x.group(1).startswith('impyrt'))
            text = 'A generated blurb about the note.'
            item['contentMd'] = md[:m.start()] + f'[TK]{m.group(1)}[=]{text}[/TK]' + md[m.end():]
            item['revision'] += 1
            return 200, {'text': text, 'model': '@cf/google/gemma-4-26b-a4b-it', 'contentMd': item['contentMd'],
                         'revision': item['revision']}
        if parts[0] == 'items' and parts[2] == 'publish':
            item = self.items[parts[1]]
            assert set(body) <= {'expectedRevision', 'note', 'noteGenerated', 'changeCategory'}, 'strict schema'
            bad = self.conflict(item, body)
            if bad:
                return bad
            unfilled = [x for x in re.finditer(r'\[TK\](.*?)\[/TK\]', item['contentMd'], re.S)
                        if '[=]' not in x.group(1) and not x.group(1).startswith('impyrt')]
            if unfilled:
                return 400, err('invalid-input', 'one or more TK scopes are not publish-ready')
            item.update(status='public', dirty=False, version=item['version'] + 1, revision=item['revision'] + 1)
            return 200, {'ok': True, 'version': item['version'], 'revision': item['revision']}
        if path == '/hoppers':
            return self.page(self.hoppers, query)
        if parts[0] == 'hoppers' and len(parts) == 3 and parts[2] == 'memberships':
            return self.page(self.memberships.get(parts[1], []), query)
        if path == '/subscriptions':
            return self.page(self.subs, query)
        return 404, err('not-found', f'no route {method} {path}')


class FakeAI:
    """Workers AI REST: answers selection prompts with `selection`, blurb prompts with `blurb`."""

    def __init__(self, selection=None, blurb='A blurb. ' * 30, status=200):
        self.selection, self.blurb, self.status = selection, blurb, status
        self.prompts = []

    def transport(self, method, url, headers, data):
        user = json.loads(data)['messages'][1]['content']
        self.prompts.append(user)
        if self.status != 200:
            return self.status, {}, b'{"errors":[{"message":"boom"}]}'
        text = self.selection if 'Candidates:' in user else self.blurb
        if callable(text):
            text = text(user)
        return 200, {}, json.dumps({'success': True, 'result': {'response': text}}).encode()


def good_selection(prompt):
    keys = re.findall(r'^\[(C\d\d)\]', prompt, re.M)
    return json.dumps({'featured': keys[1], 'why': 'it fits',
                       'did_you_know': [{'key': k, 'hook': f'that fact number {i} is quite surprising indeed'}
                                        for i, k in enumerate(keys[2:7])]})


def run(corpus, studio, ai, history, *, create=False, members_only=False, front_id=None, dry_run=False, now=NOW,
        blurb_via='tk'):
    api = F.BlygApi(API, 'tok', transport=studio.transport, dry_run=dry_run, write_interval=0) if studio else None
    wai = F.WorkersAI('acct', 'k', transport=ai.transport) if ai else None
    front = F.FrontPage(corpus, api=api, ai=wai, site=SITE, history=history, front_id=front_id,
                        create=create, members_only=members_only, dry_run=dry_run, now=now, save=False,
                        blurb_via=blurb_via)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        report = front.run()
    report['ai_calls'] = wai.calls if wai else 0
    report['log'] = out.getvalue()
    return report


def tk_scopes(md):
    return list(re.finditer(r'\[TK\].*?\[/TK\]', md, re.S))


# ---------------------------------------------------------------- tests

class ShortlistTest(unittest.TestCase):
    def setUp(self):
        self.c = make_corpus()

    def test_filters(self):
        paths = {n.path for n in F.shortlist(self.c, set())}
        for excluded in ('raw-notes/aneesh/index.md', 'raw-notes/commons/glossary/README.md', 'wiki/README.md',
                         'raw-notes/aneesh/concepts/stub.md', 'raw-notes/florian/unpublished.md',
                         'raw-notes/commons/contributions/essay/essay-p01.md'):
            self.assertNotIn(excluded, paths)
        self.assertIn('raw-notes/commons/glossary/legibility.md', paths)

    def test_inbound_links_and_score_order(self):
        self.assertEqual(self.c.inbound['raw-notes/commons/glossary/legibility.md'], 4)
        first = F.shortlist(self.c, set())[0]
        self.assertEqual(first.path, 'raw-notes/commons/glossary/legibility.md')

    def test_group_cap(self):
        utopia = [n for n in F.shortlist(self.c, set(), per_group=1) if n.path.startswith(
            'raw-notes/commons/reading/more-utopia/')]
        self.assertEqual(len(utopia), 1)
        utopia2 = [n for n in F.shortlist(self.c, set(), per_group=2) if n.path.startswith(
            'raw-notes/commons/reading/more-utopia/')]
        self.assertEqual(len(utopia2), 2)

    def test_history_exclusion_window(self):
        history = {'days': {
            '2026-10-01': {'featured': {'path': 'raw-notes/commons/glossary/legibility.md'},
                           'dyk': [{'path': 'raw-notes/sean/reoccupation.md'}]},
            '2026-06-01': {'featured': {'path': 'raw-notes/florian/drainage.md'}, 'dyk': []},
        }}
        recent = F.recent_paths(history, NOW.date())
        self.assertEqual(recent, {'raw-notes/commons/glossary/legibility.md', 'raw-notes/sean/reoccupation.md'})
        paths = {n.path for n in F.shortlist(self.c, recent)}
        self.assertNotIn('raw-notes/commons/glossary/legibility.md', paths)
        self.assertNotIn('raw-notes/sean/reoccupation.md', paths)
        self.assertIn('raw-notes/florian/drainage.md', paths)  # 154 days ago: eligible again

    def test_books(self):
        books = self.c.books()
        self.assertEqual([(s, t) for s, t, _ in books], [('mann-1493', 'Mann 1493'), ('more-utopia', 'Utopia')])
        self.assertEqual(dict((s, p) for s, _, p in books)['more-utopia'], 'raw-notes/commons/summaries/more-utopia.md')
        self.assertEqual(dict((s, p) for s, _, p in books)['mann-1493'],
                         'raw-notes/commons/reading/mann-1493/mann-1493-01.md')


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.c = make_corpus()
        self.cands = F.shortlist(self.c, set())

    def test_valid_answer(self):
        data = {'featured': 'C02', 'did_you_know': [
            {'key': 'C01', 'hook': '…that the census made people readable?'},
            {'key': 'C03', 'hook': 'Did you know that gold became chamber pots'},
            {'key': 'C02', 'hook': 'that the featured note cannot also be a hook'},
            {'key': 'C04', 'hook': 'that [[links]] and [TK] grammar are stripped from hooks'},
            {'key': 'C04', 'hook': 'that a second hook for the same note is dropped'},
            {'key': 'C99', 'hook': 'that unknown keys are dropped too'},
            {'key': 'C05', 'hook': 'no leading that, so it is dropped entirely'},
            {'key': 'C06', 'hook': 'that silver flowed from Potosí to Manila'},
        ]}
        pick = F.validate_selection(data, self.cands)
        self.assertIs(pick['featured'], self.cands[1])
        self.assertEqual([n for n, _ in pick['dyk']], [self.cands[0], self.cands[2], self.cands[3], self.cands[5]])
        hooks = [h for _, h in pick['dyk']]
        self.assertEqual(hooks[0], 'that the census made people readable')
        self.assertEqual(hooks[1], 'that gold became chamber pots')
        self.assertNotIn('[', hooks[2])
        self.assertNotIn('TK', hooks[2])

    def test_rejects_bad_answers(self):
        for data in ({'featured': 'C77', 'did_you_know': []},
                     {'featured': 'C01', 'did_you_know': [{'key': 'C02', 'hook': 'that only one is not enough'}]},
                     ['not', 'an', 'object']):
            with self.assertRaises(ValueError):
                F.validate_selection(data, self.cands)
        with self.assertRaises(ValueError):
            F.parse_json_object('I think the best note is C03.')
        self.assertEqual(F.parse_json_object('```json\n{"featured": "C01"}\n```'), {'featured': 'C01'})

    def test_junk_falls_back_to_deterministic(self):
        studio = FakeStudio()
        r = run(self.c, studio, FakeAI(selection='Sure! Here are my picks: C01, C02.'), {'days': {}}, create=True)
        self.assertEqual(r['chosen_by'], 'fallback')
        self.assertIn('using the deterministic order', r['log'])
        self.assertTrue(r['published'])
        md = next(iter(studio.items.values()))['contentMd']
        self.assertIn(F.DYK_FALLBACK_HEADING, md)
        self.assertIn(self.c.item_id(self.cands[0].path), md.split(F.DYK_FALLBACK_HEADING)[0])

    def test_ai_http_error_falls_back(self):
        studio = FakeStudio()
        r = run(self.c, studio, FakeAI(status=500), {'days': {}}, create=True)
        self.assertEqual(r['chosen_by'], 'fallback')
        self.assertTrue(r['published'])

    def test_no_ai_credentials(self):
        r = run(self.c, FakeStudio(), None, {'days': {}}, create=True)
        self.assertEqual((r['chosen_by'], r['ai_calls']), ('fallback', 0))


class PageTest(unittest.TestCase):
    def setUp(self):
        self.c = make_corpus()

    def test_create_uses_one_tk_call_and_keeps_links_outside_generated_text(self):
        studio, ai = FakeStudio(), FakeAI(selection=good_selection)
        history = {'days': {}}
        r = run(self.c, studio, ai, history, create=True)
        self.assertEqual((r['chosen_by'], r['blurb'], r['ai_calls']), ('ai', 'tk', 1))
        self.assertEqual(len(studio.writes('/generate')), 1)
        self.assertFalse([c for c in studio.calls if c[1] == '/settings' and c[0] != 'GET'], 'must not set front_page')
        md = next(iter(studio.items.values()))['contentMd']
        for m in tk_scopes(md):
            self.assertNotRegex(m.group(0)[4:-5].split('[=]')[-1], r'\[\[', 'a link inside generated text')
        dyk = md.split(F.DYK_HEADING)[1].split(F.MEMBERS_HEADING)[0]
        lines = [l for l in dyk.splitlines() if l.startswith('- ')]
        self.assertEqual(len(lines), 5)
        for line in lines:
            self.assertRegex(line, r'^- …\[TK\]impyrt @cf/google/gemma-4-26b-a4b-it=that [^\[\]]+\[/TK\]\? '
                                   r'\(\[\[[0-9a-z]{26} \| [^\]]+\]\]\)$')
        featured = md.split(F.FEATURED_HEADING)[1].split(F.DYK_HEADING)[0]
        self.assertIn('[=]A generated blurb about the note.[/TK]', featured)
        self.assertIn('| Read the full note →]]', featured)
        self.assertIn('2026-11-02', history['days'])
        self.assertEqual(history['days']['2026-11-02']['blurb'], 'tk')

    def test_tk_budget_spent_falls_back_to_impyrt_then_excerpt(self):
        studio = FakeStudio()
        studio.generate_status = 429
        r = run(self.c, studio, FakeAI(selection=good_selection), {'days': {}}, create=True)
        self.assertEqual(r['blurb'], 'impyrt')
        self.assertEqual(r['ai_calls'], 2)
        md = next(iter(studio.items.values()))['contentMd']
        self.assertIn('[TK]impyrt @cf/google/gemma-4-26b-a4b-it=A blurb.', md)
        self.assertTrue(r['published'])

        studio = FakeStudio()
        studio.generate_status = 502
        r = run(self.c, studio, FakeAI(selection=good_selection, blurb='Too short.'), {'days': {}}, create=True)
        self.assertEqual(r['blurb'], 'excerpt')
        md = next(iter(studio.items.values()))['contentMd']
        featured = md.split(F.FEATURED_HEADING)[1].split(F.DYK_HEADING)[0]
        self.assertNotIn('[TK]', featured)
        self.assertIn('*From the note itself', featured)
        self.assertTrue(r['published'])

    def test_no_republish_when_unchanged(self):
        studio, history = FakeStudio(), {'days': {}}
        run(self.c, studio, FakeAI(selection=good_selection), history, create=True)
        front_id = next(iter(studio.items))
        studio.calls.clear()
        # Same day, daily run: keeps the block, nothing changed, nothing written, no AI.
        r = run(self.c, studio, FakeAI(selection=good_selection), history, front_id=front_id)
        self.assertEqual((r['published'], r['ai_calls']), (False, 0))
        self.assertEqual(studio.writes(), [])
        self.assertIn('unchanged; not republishing', r['log'])
        # Evening run: same.
        r = run(self.c, studio, None, history, front_id=front_id, members_only=True)
        self.assertFalse(r['published'])
        self.assertEqual(studio.writes(), [])

    def test_members_change_republishes_but_keeps_featured(self):
        studio, history = FakeStudio(), {'days': {}}
        run(self.c, studio, FakeAI(selection=good_selection), history, create=True)
        front_id = next(iter(studio.items))
        before = F.featured_block_of(studio.items[front_id]['contentMd'])
        studio.hoppers = [{'id': 'h1', 'slug': 'members', 'public': True}]
        studio.subs = [{'id': 's1', 'origin': 'https://venkateshrao.com/blyg/', 'title': 'Venkat'}]
        studio.memberships = {'h1': [
            {'hopperId': 'h1', 'subscriptionId': 's1', 'remoteId': rid(1, 'r'), 'addedAt': '2026-11-02T00:00:00Z',
             'item': {'subscriptionId': 's1', 'remoteId': rid(1, 'r'), 'kind': 'thread', 'state': 'current',
                      'contentMd': '# Machines [and] men\n\nBody', 'author': {'name': 'Venkatesh Rao'},
                      'page': None, 'l0': False}},
            {'hopperId': 'h1', 'subscriptionId': 's1', 'remoteId': rid(2, 'r'), 'addedAt': '2026-11-01T00:00:00Z',
             'item': None}]}
        studio.calls.clear()
        r = run(self.c, studio, None, history, front_id=front_id, members_only=True)
        self.assertTrue(r['published'])
        self.assertEqual(len(studio.writes('/publish')), 1)
        self.assertEqual(studio.writes('/publish')[0][2]['changeCategory'], 'minor')
        self.assertIsInstance(studio.writes('/publish')[0][2]['expectedRevision'], int)
        self.assertEqual(studio.writes('/generate'), [])
        md = studio.items[front_id]['contentMd']
        self.assertEqual(F.featured_block_of(md), before)
        self.assertIn(f'- [Machines and men](https://venkateshrao.com/blyg/t/{rid(1, "r")}/) — Venkatesh Rao', md)

    def test_concurrent_edit_rereads_revision_and_retries(self):
        studio, history = FakeStudio(), {'days': {}}
        run(self.c, studio, FakeAI(selection=good_selection), history, create=True)
        front_id = next(iter(studio.items))
        route = studio.route
        bumped = []

        def edit_first(method, path, query, body):
            if method == 'PATCH' and not bumped:  # the owner saves in Studio between our read and our write
                bumped.append(1)
                studio.items[front_id]['revision'] += 1
            return route(method, path, query, body)

        studio.route = edit_first
        studio.calls.clear()
        r = run(self.c, studio, FakeAI(selection=good_selection), history, front_id=front_id,
                now=datetime(2026, 11, 3, 6, 30, tzinfo=timezone.utc))
        self.assertTrue(r['published'])
        patches = studio.writes()[:2]
        self.assertEqual([c[0] for c in patches], ['PATCH', 'PATCH'])
        self.assertEqual(patches[1][2]['expectedRevision'], patches[0][2]['expectedRevision'] + 1)
        self.assertIn('re-reading and retrying once', r['log'])

    def test_own_member_post_read_from_items(self):
        studio = FakeStudio()
        studio.items['o' * 26] = {'id': 'o' * 26, 'revision': 2, 'kind': 'fragment', 'status': 'public',
                                  'updated': '2026-11-01T00:00:00Z', 'contentMd': 'An own note\n\nbody'}
        studio.hoppers = [{'id': 'h1', 'slug': 'members', 'public': True}]
        studio.memberships = {'h1': [{'hopperId': 'h1', 'subscriptionId': '~own', 'remoteId': 'o' * 26,
                                      'addedAt': '2026-11-01T00:00:00Z', 'item': None}]}
        posts = F.member_posts(F.BlygApi(API, 'tok', transport=studio.transport, write_interval=0), SITE, 'members')
        self.assertEqual(posts, [{'title': 'An own note', 'author': '', 'url': f'{SITE}f/{"o" * 26}/'}])

    def test_next_day_chooses_again_and_excludes_yesterday(self):
        studio, history = FakeStudio(), {'days': {}}
        run(self.c, studio, FakeAI(selection=good_selection), history, create=True)
        front_id = next(iter(studio.items))
        yesterday = history['days']['2026-11-02']
        r = run(self.c, studio, FakeAI(selection=good_selection), history, front_id=front_id,
                now=datetime(2026, 11, 3, 6, 30, tzinfo=timezone.utc))
        self.assertTrue(r['published'])
        today = history['days']['2026-11-03']
        used = {yesterday['featured']['path']} | {d['path'] for d in yesterday['dyk']}
        self.assertNotIn(today['featured']['path'], used)
        self.assertFalse(used & {d['path'] for d in today['dyk']})

    def test_empty_members_is_graceful(self):
        md = F.members_section(None, [], SITE, 'members')
        self.assertIn('Nothing from member blygs yet', md)
        self.assertIn('https://worldmachines.org/hoppers', md)
        studio = FakeStudio()
        studio.hoppers = [{'id': 'h1', 'slug': 'members', 'public': True}]
        r = run(self.c, studio, None, {'days': {}}, create=True)
        self.assertTrue(r['published'])
        self.assertIn('Nothing from member blygs yet', next(iter(studio.items.values()))['contentMd'])

    def test_latest_digest_linked(self):
        studio = FakeStudio()
        studio.items['d' * 26] = {'id': 'd' * 26, 'revision': 3, 'status': 'public', 'updated': '2026-11-02T06:00:00Z',
                                  'contentMd': '# World Machines digest — 2026-11-02 (morning)\n\n…'}
        run(self.c, studio, None, {'days': {}}, create=True)
        md = [i for i in studio.items.values() if i['id'] != 'd' * 26][0]['contentMd']
        self.assertIn(f'Latest digest: [[{"d" * 26} | World Machines digest — 2026-11-02 (morning)]]', md)

    def test_dry_run_writes_nothing(self):
        studio = FakeStudio()
        r = run(self.c, studio, FakeAI(selection=good_selection), {'days': {}}, dry_run=True)
        self.assertEqual(studio.writes(), [])
        self.assertIn('----- front page markdown -----', r['log'])
        self.assertIn(F.DYK_HEADING, r['log'])

    def test_unresolvable_link_is_unlinked_and_retried(self):
        content = 'See [[aaaaaaaaaaaaaaaaaaaaaaaaaa | A note]] and [[bbbbbbbbbbbbbbbbbbbbbbbbbb | B]].'
        err = F.BlygError(400, 'POST', '/items/x/publish', {
            'code': 'invalid-input', 'message': 'one or more references do not resolve',
            'details': {'errors': [{'directive': '[[aaaaaaaaaaaaaaaaaaaaaaaaaa | A note]]', 'reason': 'item is withdrawn'}]}})
        ids = F.unresolved_link_ids(err)
        self.assertEqual(ids, {'a' * 26})
        self.assertEqual(F.unlink(content, ids), 'See A note and [[bbbbbbbbbbbbbbbbbbbbbbbbbb | B]].')


class HistoryFileTest(unittest.TestCase):
    def test_save_prunes_and_sorts(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'h' / 'history.json'
            h = {'version': 1, 'days': {'2026-11-02': {'x': 1}, '2024-01-01': {'x': 0}}}
            F.save_history(h, path, NOW.date())
            self.assertEqual(list(json.loads(path.read_text())['days']), ['2026-11-02'])
            self.assertEqual(F.load_history(path)['days']['2026-11-02'], {'x': 1})
            self.assertEqual(F.load_history(Path(d) / 'missing.json'), {'version': 1, 'days': {}})


if __name__ == '__main__':
    unittest.main()
