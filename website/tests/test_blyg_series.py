"""Tests for scripts/blyg_series.py (the weekly series posts) and its front-page dispatch.

Run from website/:  python -m unittest discover -s tests
Reuses the FakeStudio / FakeAI harness of test_blyg_front.py, extended with the
routes the series uses (contacts, hoppers) and with Studio's partial-quote check.
"""
import contextlib
import io
import json
import re
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_blyg_front import API, SITE, FakeAI, FakeStudio, err, good_selection, note, rid  # noqa: E402

import blyg_front as F  # noqa: E402
import blyg_series as S  # noqa: E402
import corpus as C  # noqa: E402

MON = datetime(2026, 11, 9, 6, 30, tzinfo=timezone.utc)
DAYS = {name: datetime(2026, 11, 9 + i, 6, 30, tzinfo=timezone.utc) for i, name in enumerate(
    ['monday', 'questions', 'concepts', 'books', 'side-by-side', 'terms', 'oracle'])}

LEG_DEF = ('Legibility is the condition of being readable by a system that has the power to act on what it reads, '
           'and so to change it.')


def filler(topic, n=12):
    return ' '.join(f'Filler sentence number {i} about {topic} keeps this note long enough for the shortlist rules '
                    f'to treat it as a real note.' for i in range(n))


def series_corpus():
    notes = [
        note('raw-notes/commons/glossary/legibility.md', 'Legibility',
             f'## Definition\n\n{LEG_DEF}\n\n{filler("legibility")}'),
        note('raw-notes/aneesh/concepts/modernity-machine.md', 'Modernity Machine',
             'The Modernity Machine optimized for [[legibility]] because scale requires every subject to be counted, '
             'mapped, measured and ordered by a distant office.\n\n'
             'Reading [[more-utopia-01|Hythloday]] taught the group that a perfectly legible island is also a '
             'perfectly governed one, which is the whole of its horror.\n\n'
             f'{filler("modernity")}\n\n'
             '## Open\n\nWhether the machine can survive once its own legibility starts to fail is the question this '
             'note leaves for the group to settle?'),
        note('raw-notes/sean/reoccupation.md', 'Reoccupation',
             'Blumenberg would say that [[legibility]] reoccupies the vacant position once held by providence, so the '
             'state reads its subjects as God was said to read souls.\n\n'
             'The idea of the [[modernity-machine|Modernity Machine]] is a reoccupation too, filling the slot that '
             'progress left open when its promises stopped arriving.\n\n'
             f'{filler("reoccupation")}\n\n'
             '## Open\n\nWhat would it take for a vacant position to stay vacant long enough for something new to '
             'grow there instead of a replacement?'),
        note('raw-notes/florian/drainage.md', 'Hilarious drainage',
             'Every drain in the old city was a small act of [[legibility]], since a mapped sewer let the engineers '
             'predict where the water and the cholera would go.\n\n'
             'The [[modernity-machine|Modernity Machine]] shows itself most clearly in the plumbing, where nobody '
             'thought to hide what it was doing to the people above.\n\n'
             f'{filler("drains")}\n\n'
             'So who decides which drains get mapped, and who is left living above the ones that never are?',
             connects='[[legibility]]'),
        note('raw-notes/commons/synthesis/bourgeois.md', 'Bourgeois inwardness',
             'The diary was a defence against [[legibility]], a place where the self could be written without '
             'being read by the household, the church or the state.\n\n' + filler('diaries')),
        note('raw-notes/commons/summaries/more-utopia.md', 'Utopia (Thomas More, 1516)', filler('Utopia')),
        note('raw-notes/commons/reading/more-utopia/more-utopia-01.md', 'Hythloday', filler('counsel')),
        note('raw-notes/commons/reading/more-utopia/more-utopia-02.md', 'Gold chamber pots', filler('gold')),
        note('raw-notes/aneesh/index.md', 'Aneesh index', '[[modernity-machine]] [[legibility]]'),
    ]
    # Padding, so the front page's featured note and hooks have a pool to draw from for a week.
    notes += [note(f'raw-notes/commons/entities/entity-{i:02d}.md', f'Entity {i}', filler(f'entity {i}'))
              for i in range(24)]
    state = {n.path: {'id': rid(i), 'published_version': 1} for i, n in enumerate(notes)}
    authors = C.Authors(authors={'aneesh': {'name': 'Aneesh Sathe', 'blyg': 'https://blyg.aneeshsathe.com/'},
                                 'sean': {'name': 'Sean Stevenson', 'blyg': None},
                                 'florian': {'name': 'Florian Lohse', 'blyg': None}}, handles={})
    return F.Corpus(notes=notes, state=state, authors=authors, config_path=None)


READING = ('The cast speaks of steady progress under a firm hand, and the question is whether the machine can '
           'keep that hand once what it reads stops answering back. ' * 4).strip()


def oracle_ai(selection=good_selection):
    def blurb(prompt):
        return READING + '\n\n' + READING if 'The cast' in prompt else 'A blurb. ' * 30
    return FakeAI(selection=selection, blurb=blurb)


class SeriesStudio(FakeStudio):
    """FakeStudio plus contacts, hoppers and Studio's check that a partial quote is in its target's text."""

    def __init__(self, corpus):
        super().__init__()
        self.corpus = corpus
        self.contacts = []
        self.filed = []
        self.refuse_quotes = set()
        self.by_id = {e['id']: p for p, e in corpus.state.items()}

    def target_text(self, item_id):
        path = self.by_id.get(item_id)
        return F.plain(self.corpus.by_path[path].body) if path else ''

    def route(self, method, path, query, body):
        parts = path.strip('/').split('/')
        if path == '/contacts' and method == 'GET':
            return 200, {'contacts': self.contacts}
        if path == '/hoppers' and method == 'POST':
            h = {'id': f'h{len(self.hoppers) + 1}', 'slug': body['name'], 'name': body['name'], 'public': False}
            self.hoppers.append(h)
            return 201, h
        if parts[0] == 'hoppers' and len(parts) == 2 and method == 'PATCH':
            h = next(h for h in self.hoppers if h['id'] == parts[1])
            h.update(body)
            return 200, h
        if parts[0] == 'hoppers' and len(parts) == 5 and parts[2] == 'items' and method == 'PUT':
            self.filed.append((parts[1], parts[3], parts[4]))
            return 200, {'ok': True}
        if parts[0] == 'items' and len(parts) == 3 and parts[2] == 'publish':
            item = self.items[parts[1]]
            errors = []
            for m in re.finditer(r'^!\[\[([0-9a-z]{26})\]\]\n> (.*)$', item['contentMd'], re.M):
                if m.group(1) in self.refuse_quotes or m.group(2) not in self.target_text(m.group(1)):
                    errors.append({'directive': f'![[{m.group(1)}]]',
                                   'reason': "quoted passage not found in the target's version 1"})
            if errors:
                return 400, err('invalid-input', 'one or more references do not resolve', errors=errors)
        if path == '/items' and method == 'POST':
            status, item = super().route(method, path, query, body)
            item['created'] = item['updated']
            return status, item
        return super().route(method, path, query, body)


def builder(corpus, today, history=None, **kw):
    return S.Builder(corpus, S.Texts(corpus), site=SITE, today=today, history=history or {'days': {}}, **kw)


def front(corpus, studio, ai, history, now, front_id=None, create=False, dry_run=False):
    api = F.BlygApi(API, 'tok', transport=studio.transport, dry_run=dry_run, write_interval=0) if studio else None
    wai = F.WorkersAI('acct', 'k', transport=ai.transport) if ai else None
    page = F.FrontPage(corpus, api=api, ai=wai, site=SITE, history=history, front_id=front_id, create=create,
                       now=now, save=False, dry_run=dry_run)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        report = page.run()
    report['ai_calls'] = wai.calls if wai else 0
    report['log'] = out.getvalue()
    return report


def series_items(studio, stype):
    return [i for i in studio.items.values() if S.series_type_of(i['contentMd']) == stype]


def quotes_in(md):
    return re.findall(r'^!\[\[([0-9a-z]{26})\]\]\n> (.*)$', md, re.M)


AT_HANDLE = re.compile(r'(?<![\w@./:+-])@([A-Za-z0-9][A-Za-z0-9_-]{0,38})(?![\w@]|[.-]\w)')


def bare_handles(md):
    """@handles Studio would try to resolve: outside quotes, links and TK scopes (whose impyrt names a model)."""
    md = re.sub(r'\[TK\].*?\[/TK\]', '', md, flags=re.S)
    md = re.sub(r'!?\[\[[^\]\n]*\]\]|!?\[[^\]\n]*\]\([^)\n]*\)', '', md)
    md = re.sub(r'^\s{0,3}>.*$', '', md, flags=re.M)
    return set(AT_HANDLE.findall(md))


# ---------------------------------------------------------------- tests

class DispatchTest(unittest.TestCase):
    def test_weekdays(self):
        got = {name: S.series_for(dt.date()) for name, dt in DAYS.items()}
        self.assertEqual(got, {'monday': None, 'questions': 'questions', 'concepts': 'concepts', 'books': 'books',
                               'side-by-side': 'side-by-side', 'terms': 'terms', 'oracle': 'oracle'})


class QuoteTest(unittest.TestCase):
    def test_quotable_rules(self):
        self.assertTrue(S.quotable(LEG_DEF))
        for bad in ('Too short to quote.', LEG_DEF.replace('system', '*system*'), LEG_DEF.replace('.', ':'),
                    LEG_DEF.replace('Legibility', '1. Legibility'), LEG_DEF + ' See https://example.com now.',
                    LEG_DEF.replace('power', '[power]'), LEG_DEF.replace('power', 'power & might'),
                    ' '.join(['word'] * 61) + '.'):
            self.assertFalse(S.quotable(bad), bad)

    def test_sentences_skip_lists_code_and_unlabelled_links(self):
        n = note('raw-notes/sean/x.md', 'X', '\n\n'.join([
            'A plain paragraph sentence that is long enough to be quoted by the series without any trouble at all.',
            '- A list item sentence that is long enough to be quoted by the series but sits inside a list.',
            '    An indented code block sentence that is long enough to be quoted but is really code.',
            'A line that ends in a hard break and is long enough to quote, but only up to the break  \n'
            'and this half follows the break so a quote across it would fail at Studio.',
        ]))
        c = F.Corpus(notes=[n], state={n.path: {'id': rid(1), 'published_version': 1}},
                     authors=C.Authors(authors={'sean': {'name': 'Sean Stevenson'}}, handles={}), config_path=None)
        texts = [s.text for s in S.Texts(c).sentences(n)]
        self.assertEqual(texts, ['A plain paragraph sentence that is long enough to be quoted by the series without '
                                 'any trouble at all.'])

    def test_slug_labels_only_where_asked(self):
        n = note('raw-notes/commons/synthesis/s.md', 'S',
                 'Christopher Clark in [[clark-spring]] uses Herzen as a witness to the European revolutions of the '
                 'year rather than as a precursor of anything that came later.')
        t = note('raw-notes/commons/reading/clark-spring/clark-spring-01.md', 'clark-spring', filler('spring'))
        c = F.Corpus(notes=[n, t], state={n.path: {'id': rid(1), 'published_version': 1},
                                          t.path: {'id': rid(2), 'published_version': 1}},
                     authors=C.Authors(authors={}, handles={}), config_path=None)
        texts = S.Texts(c)
        self.assertEqual(texts.sentences(n), [])
        self.assertEqual(len(texts.sentences(n, slugs=True)), 1)
        self.assertIn('clark-spring uses Herzen', texts.sentences(n, slugs=True)[0].text)

    def test_changed_note_is_never_quoted(self):
        c = series_corpus()
        c.state['raw-notes/sean/reoccupation.md']['published_sha'] = 'not-what-the-repo-renders'
        t = S.Texts(c)
        self.assertIsNone(t.rendered(c.by_path['raw-notes/sean/reoccupation.md']))
        self.assertEqual(t.sentences(c.by_path['raw-notes/sean/reoccupation.md']), [])
        self.assertTrue(t.sentences(c.by_path['raw-notes/florian/drainage.md']))


class RelabelTest(unittest.TestCase):
    """The 2026-11 relabel adds an AI byline to commons notes; quotes must survive it, before and after."""

    def test_commons_note_quotable_with_or_without_the_ai_byline(self):
        n = note('raw-notes/commons/reading/book/book-01.md', 'Chapter one',
                 'A plain paragraph sentence that is long enough to be quoted by the series without any trouble.')
        state = {n.path: {'id': rid(1), 'published_version': 1}}
        c = F.Corpus(notes=[n], state=state, authors=C.Authors(authors={}, handles={}), config_path=None)
        t = S.Texts(c)
        line = S.load_ai_bylines()['raw-notes/commons/reading/']
        unit = t.renderer.units_by_note[n.path][0]
        for byline in ('', line):
            state[n.path]['published_sha'] = C.sha(t.renderer.render(unit, byline, t._pub_id))
            t._rendered.clear()
            t._sentences.clear()
            self.assertIsNotNone(t.rendered(n), repr(byline))
            self.assertEqual(len(t.sentences(n)), 1, repr(byline))
        state[n.path]['published_sha'] = 'something else'
        t._rendered.clear()
        self.assertIsNone(t.rendered(n))

    def test_real_config_has_the_reading_line(self):
        self.assertIn('not by a member', S.load_ai_bylines()['raw-notes/commons/reading/'])


class BuildersTest(unittest.TestCase):
    def setUp(self):
        self.c = series_corpus()

    def build(self, stype, history=None, **kw):
        b = builder(self.c, DAYS[stype].date(), history, **kw)
        with contextlib.redirect_stdout(io.StringIO()):
            post = S.BUILDERS[stype](b)
        return post

    def test_every_builder_writes_valid_grammar_and_verbatim_quotes(self):
        ai = F.WorkersAI('a', 'k', transport=oracle_ai().transport)
        for stype in S.TYPES:
            post = self.build(stype, ai=ai)
            self.assertIsNotNone(post, stype)
            md = post.markdown
            self.assertTrue(S.check_grammar(post), stype)
            self.assertTrue(md.startswith(S.TITLE_PREFIXES[stype]), stype)
            scopes = re.findall(r'\[TK\](.*?)\[/TK\]', md, re.S)
            self.assertLessEqual(len(scopes), S.MAX_SCOPES)
            gen = [x for x in scopes if not x.startswith('impyrt')]
            self.assertEqual(len(gen), post.scopes, stype)
            for body in gen:
                self.assertLessEqual(len(re.findall(r'!\[\[', body)), S.MAX_SOURCES)
                self.assertNotRegex(body, r'(?<!!)\[\[', f'{stype}: a link inside a scope')
            self.assertTrue(quotes_in(md), stype)
            for item_id, text in quotes_in(md):
                path = next(p for p, e in self.c.state.items() if e['id'] == item_id)
                self.assertIn(text, F.plain(self.c.by_path[path].body), f'{stype}: not verbatim')
            self.assertFalse(bare_handles(md), stype)
            self.assertEqual(series_line_day(md), DAYS[stype].date().isoformat())

    def test_questions(self):
        post = self.build('questions')
        self.assertIn(post.subject, {'raw-notes/aneesh/concepts/modernity-machine.md', 'raw-notes/sean/reoccupation.md',
                                     'raw-notes/florian/drainage.md'})
        self.assertIn('## Notes that bear on it', post.markdown)
        q = quotes_in(post.markdown)[0][1]
        self.assertTrue(q.endswith('?'), q)

    def test_closing_question_ignores_the_importer_footer(self):
        b = builder(self.c, DAYS['questions'].date())
        drainage = self.c.by_path['raw-notes/florian/drainage.md']
        self.assertIn('**Connects:**', b.t.rendered(drainage))
        self.assertTrue(S.question_of(b, drainage).text.startswith('So who decides which drains get mapped'))

    def test_concept_starts_with_legibility_and_spreads_authors(self):
        post = self.build('concepts')
        self.assertEqual(post.subject, 'raw-notes/commons/glossary/legibility.md')
        self.assertIn(f'> {LEG_DEF}', post.markdown)
        uses = post.markdown.split('## How members use it')[1].split('## Where')[0]
        names = re.findall(r'^— ([^,\n]+), in', uses, re.M)
        self.assertEqual(len(names), len(set(names)), names)   # one quote per member
        self.assertGreaterEqual(len(names), 3)

    def test_side_by_side_two_authors(self):
        post = self.build('side-by-side')
        authors = re.findall(r'^— ([^,\n]+), in', post.markdown, re.M)
        self.assertEqual(len(authors), 2)
        self.assertNotEqual(authors[0], authors[1])
        self.assertIn('never invent a disagreement', post.markdown)

    def test_terms_need_two_authors(self):
        post = self.build('terms')
        authors = {self.c.author_key(self.c.by_path[p]) for p in post.sources}
        self.assertGreaterEqual(len(authors), 2)

    def test_books_link_summary_and_chapters(self):
        post = self.build('books')
        self.assertEqual(post.subject, 'more-utopia')
        for p in ('raw-notes/commons/summaries/more-utopia.md', 'raw-notes/commons/reading/more-utopia/more-utopia-01.md',
                  'raw-notes/commons/reading/more-utopia/more-utopia-02.md'):
            self.assertIn(self.c.item_id(p), post.markdown)
        self.assertIn(self.c.item_id('raw-notes/aneesh/concepts/modernity-machine.md'),
                      dict(quotes_in(post.markdown)))

    def test_oracle_cast_and_reading(self):
        ai = F.WorkersAI('a', 'k', transport=oracle_ai().transport)
        post = self.build('oracle', ai=ai)
        self.assertEqual(post.scopes, 0)
        self.assertIn('[TK]impyrt @cf/google/gemma-4-26b-a4b-it=The cast speaks', post.markdown)
        self.assertIn("James Legge's translation", post.markdown)
        self.assertEqual(S.hexagram_patterns([7, 8, 8, 8, 7, 8]), ('100010', '100010'))
        self.assertEqual(S.hexagram_patterns([9, 6, 8, 8, 7, 8]), ('100010', '010010'))
        iching = S.load_iching()
        self.assertEqual(S.oracle_texts(iching, [7, 8, 8, 8, 7, 8])[0]['number'], 3)
        # The same day casts the same lines.
        rng1, rng2 = S.series_rng('oracle', DAYS['oracle'].date()), S.series_rng('oracle', DAYS['oracle'].date())
        self.assertEqual(S.cast_iching(rng1), S.cast_iching(rng2))
        # No Workers AI, no oracle post (the front page falls back).
        self.assertIsNone(self.build('oracle'))

    def test_history_excludes_subjects_for_ninety_days(self):
        first = self.build('concepts')
        day = DAYS['concepts'].date()
        history = {'days': {(day - F.timedelta(days=7)).isoformat(): {
            'series': {'type': 'concepts', 'subject': first.subject, 'subject_title': first.subject_title}}}}
        second = self.build('concepts', history)
        self.assertNotEqual(getattr(second, 'subject', None), first.subject)
        old = {'days': {(day - F.timedelta(days=91)).isoformat(): {
            'series': {'type': 'concepts', 'subject': first.subject, 'subject_title': first.subject_title}}}}
        self.assertEqual(self.build('concepts', old).subject, first.subject)
        # Another type's history does not exclude it.
        other = {'days': {(day - F.timedelta(days=7)).isoformat(): {'series': {'type': 'terms', 'subject': first.subject}}}}
        self.assertEqual(self.build('concepts', other).subject, first.subject)

    def test_handles_only_for_known_contacts(self):
        contacts = [{'id': 'c1', 'handle': 'sean', 'name': 'Sean Stevenson', 'url': 'https://sean.example/'},
                    {'id': 'c2', 'handle': 'aneesh', 'name': 'Someone Else', 'url': 'https://blyg.aneeshsathe.com/'}]
        for stype in ('questions', 'concepts', 'side-by-side', 'terms'):
            post = self.build(stype, contacts=contacts)
            self.assertLessEqual(bare_handles(post.markdown), {'sean', 'aneesh'}, stype)
            self.assertNotIn('@Florian', post.markdown)
            for body in re.findall(r'\[TK\](.*?)\[/TK\]', post.markdown, re.S):
                self.assertNotIn('@', body)
        post = self.build('concepts', contacts=contacts)
        self.assertIn('— @sean, in', post.markdown)
        self.assertIn('— @aneesh, in', post.markdown)    # matched by blyg URL
        self.assertIn('— Florian Lohse, in', post.markdown)


def series_line_day(md):
    return S.series_line_date(md)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.c = series_corpus()

    def test_series_day_publishes_files_and_skips_the_blurb(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        r = front(self.c, studio, FakeAI(selection=good_selection), history, DAYS['concepts'], create=True)
        page_id = next(i for i in studio.items if not S.series_type_of(studio.items[i]['contentMd']))
        # create never builds a series; the next day's daily run does
        r = front(self.c, studio, FakeAI(selection=good_selection), history, DAYS['concepts'] + F.timedelta(days=1),
                  front_id=page_id)
        post = series_items(studio, 'books')
        self.assertEqual(len(post), 1)
        self.assertEqual(post[0]['status'], 'public')
        self.assertLessEqual(r['blyg_generate_calls'], 2)          # the series scope only: no featured blurb
        self.assertLessEqual(r['blyg_generate_calls'] + 1, S.RUN_TK_BUDGET)
        page = studio.items[page_id]['contentMd']
        self.assertIn(F.SERIES_HEADING + 'Book companions', page)
        self.assertNotIn(F.FEATURED_HEADING, page)
        self.assertIn(f"[[{post[0]['id']} | Read today’s post →]]", page)
        self.assertEqual([h['slug'] for h in studio.hoppers], ['books'])
        self.assertTrue(studio.hoppers[0]['public'])
        self.assertEqual(studio.hoppers[0]['name'], 'Book companions')
        self.assertIn(('h1', '~own', post[0]['id']), studio.filed)
        day = history['days']['2026-11-12']
        self.assertEqual(day['series']['type'], 'books')
        self.assertTrue(day['series']['published'])
        self.assertNotIn('featured', day)
        self.assertEqual(F.featured_block_of(page).split('\n')[0], F.SERIES_HEADING + 'Book companions')

    def test_generation_failure_falls_back_then_resumes(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        front(self.c, studio, None, history, MON, create=True)
        page_id = next(iter(studio.items))
        studio.generate_status = 429
        r = front(self.c, studio, FakeAI(selection=good_selection), history, DAYS['questions'], front_id=page_id)
        drafts = series_items(studio, 'questions')
        self.assertEqual([d['status'] for d in drafts], ['draft'])
        page = studio.items[page_id]['contentMd']
        self.assertIn(F.FEATURED_HEADING, page)            # fell back to the featured note
        self.assertEqual(r['blurb'], 'impyrt')               # its TK call was refused too
        day = history['days']['2026-11-10']
        self.assertFalse(day['series']['published'])
        self.assertIn('featured', day)
        # Next morning (a concepts day): the draft is finished first, then today's post.
        studio.generate_status = 200
        r = front(self.c, studio, FakeAI(selection=good_selection), history, DAYS['concepts'], front_id=page_id)
        self.assertEqual(studio.items[drafts[0]['id']]['status'], 'public')
        self.assertTrue(history['days']['2026-11-10']['series']['published'])
        self.assertEqual(len(series_items(studio, 'questions')), 1)   # resumed, not duplicated
        self.assertEqual([i['status'] for i in series_items(studio, 'concepts')], ['public'])
        self.assertLessEqual(r['blyg_generate_calls'], S.RUN_TK_BUDGET)
        self.assertIn('Resuming unfinished questions draft', r['log'])
        self.assertEqual({h['slug'] for h in studio.hoppers}, {'questions', 'concepts'})

    def test_refused_quote_is_dropped_and_retried_once(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        concept_id = self.c.item_id('raw-notes/commons/glossary/legibility.md')
        sean = self.c.item_id('raw-notes/sean/reoccupation.md')
        studio.refuse_quotes = {sean}
        api = F.BlygApi(API, 'tok', transport=studio.transport, write_interval=0)
        runner = S.Runner(self.c, api=api, site=SITE, history=history, today=DAYS['concepts'].date())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            r = runner.run_today('concepts')
        self.assertTrue(r['published'], out.getvalue())
        md = series_items(studio, 'concepts')[0]['contentMd']
        self.assertNotIn(f'![[{sean}]]\n>', md)
        self.assertIn(f'![[{sean}]]', md.split('[TK]')[1])   # still a source of the scope
        self.assertIn(f'![[{concept_id}]]\n> {LEG_DEF}', md)
        self.assertNotIn('— Sean Stevenson, in', md)
        self.assertEqual(len(studio.writes('/publish')), 2)

    def test_same_day_rerun_reuses_the_post(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        api = F.BlygApi(API, 'tok', transport=studio.transport, write_interval=0)
        for _ in range(2):
            runner = S.Runner(self.c, api=api, site=SITE, history=history, today=DAYS['terms'].date())
            with contextlib.redirect_stdout(io.StringIO()):
                r = runner.run_today('terms')
            self.assertTrue(r['published'])
        self.assertEqual(len(series_items(studio, 'terms')), 1)
        self.assertEqual(len(studio.writes('/generate')), 1)

    def test_budget_leaves_a_draft_for_later(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        api = F.BlygApi(API, 'tok', transport=studio.transport, write_interval=0)
        runner = S.Runner(self.c, api=api, site=SITE, history=history, today=DAYS['concepts'].date(), budget=0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(runner.run_today('concepts'))
        self.assertEqual(series_items(studio, 'concepts'), [])
        self.assertEqual(studio.writes('/generate'), [])

    def test_oracle_day_spends_no_blyg_ai(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        front(self.c, studio, None, history, MON, create=True)
        page_id = next(iter(studio.items))
        r = front(self.c, studio, oracle_ai(), history, DAYS['oracle'], front_id=page_id)
        self.assertEqual(r['blyg_generate_calls'], 0)
        self.assertEqual(r['ai_calls'], 2)    # the hooks and the reading, both Workers AI REST
        post = series_items(studio, 'oracle')
        self.assertEqual([p['status'] for p in post], ['public'])
        self.assertIn(F.SERIES_HEADING + 'Oracle casts', studio.items[page_id]['contentMd'])

    def test_monday_is_the_featured_note(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        front(self.c, studio, None, history, MON - F.timedelta(days=1), create=True)
        page_id = next(iter(studio.items))
        r = front(self.c, studio, FakeAI(selection=good_selection), history, MON, front_id=page_id)
        self.assertIn(F.FEATURED_HEADING, studio.items[page_id]['contentMd'])
        self.assertEqual(r['blyg_generate_calls'], 1)
        self.assertEqual([i for i in studio.items.values() if S.series_type_of(i['contentMd'])], [])

    def test_evening_run_keeps_the_series_block(self):
        studio, history = SeriesStudio(self.c), {'days': {}}
        front(self.c, studio, None, history, MON, create=True)
        page_id = next(iter(studio.items))
        front(self.c, studio, FakeAI(selection=good_selection), history, DAYS['terms'], front_id=page_id)
        block = F.featured_block_of(studio.items[page_id]['contentMd'])
        studio.calls.clear()
        api = F.BlygApi(API, 'tok', transport=studio.transport, write_interval=0)
        page = F.FrontPage(self.c, api=api, site=SITE, history=history, front_id=page_id, members_only=True,
                           now=DAYS['terms'].replace(hour=18), save=False)
        with contextlib.redirect_stdout(io.StringIO()):
            page.run()
        self.assertEqual(F.featured_block_of(studio.items[page_id]['contentMd']), block)
        self.assertEqual(studio.writes('/generate'), [])
        self.assertEqual(len(series_items(studio, 'terms')), 1)


class CliTest(unittest.TestCase):
    def test_series_only_dry_run_prints_markdown_offline(self):
        c = series_corpus()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            report = F.main(['--dry-run', '--no-ai', '--series-only', 'side-by-side', '--date', '2026-11-13'],
                            corpus=c)
        text = out.getvalue()
        self.assertIn('----- series post markdown (side-by-side) -----', text)
        self.assertIn('# Side by side: ', text)
        self.assertIn('Friday 2026-11-13', text)
        self.assertFalse(report['published'])

    def test_front_dry_run_on_a_series_day_shows_the_series_block(self):
        c = series_corpus()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            F.main(['--dry-run', '--no-ai', '--date', '2026-11-14'], corpus=c)
        self.assertIn(F.SERIES_HEADING + 'Term watch', out.getvalue())

    def test_date_needs_dry_run(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                F.main(['--date', '2026-11-13'], corpus=series_corpus())


if __name__ == '__main__':
    unittest.main()
