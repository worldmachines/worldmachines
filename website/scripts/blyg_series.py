#!/usr/bin/env python3
"""
The weekly rhythm of series posts on the World Machines blyg.

One series post a day, Tuesday to Sunday, chosen by the UTC weekday of the
front page's choosing run (the first run of the UTC day; see blyg_front.py).
Monday keeps the featured note.

  Tue  questions     Open questions roundup: one question a member left open,
                     quoted, with up to six notes that bear on it and one TK
                     scope on which of them bear on it and how.
  Wed  concepts      Concept dossier: a concept note's definition, quoted, then
                     one quote per note that uses it (different authors where
                     possible), one or two TK scopes on where the uses agree
                     and diverge, and a links-only list of the other notes.
  Thu  books         Book companion: a book's summary and chapter notes, quotes
                     from the notes that cite it, one TK scope on what the
                     group has taken from it.
  Fri  side-by-side  Side by side: two notes by different authors that link the
                     same concept, both quoted, one TK scope told to say plainly
                     when they agree and never to invent a disagreement.
  Sat  terms         Term watch: a term used in notes by at least two authors,
                     one quote per usage, one TK scope on whether they mean the
                     same thing.
  Sun  oracle        Oracle cast: an I Ching cast (three coins, six throws, the
                     method and Legge text WM-Divinations uses) applied to one
                     open question; the reading is one Workers AI REST call,
                     disclosed as `impyrt`. No blyg AI call.

Every post is its own thread: created as a draft, its TK scopes generated on the
blyg, published once, then filed into a public hopper per series (slugs
`questions`, `concepts`, `books`, `side-by-side`, `terms`, `oracle`), created
when missing. If generation fails (budget spent, provider error) the draft
stays and the next choosing run resumes it, as the digest does.

Quotes are partial transclusions: `![[id]]` and, on the next line, a
blockquote whose text Studio checks is a verbatim substring of the target's
text content. They are taken conservatively from the note as it was published
(re-rendered with the importer's own renderer; a note whose text has changed
since it was published is never quoted): whole sentences of 15-60 words from
plain paragraphs, with no markdown, entity, link or bracket characters except
the labels of blyg links, which render as their own text. A publish that is
refused over a quote drops that quote and retries once.

Budget: series posts and the front page share BLYG_FRONT_TOKEN (10 AI calls a
grant a day; 40 for the whole blyg). A run spends at most RUN_TK_BUDGET blyg
TK calls; a series day spends 1-2 and the front page skips its own blurb.

History: tools/blyg-front/history.json day entries gain
  "series": {"type", "id", "title", "subject", "sources", "author", "published"}
and each type keeps its own 90-day exclusion of subjects.

Stdlib only. blyg_front.py drives it; `--series-only <type>` there runs one.
"""
import json
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import blyg_front as F
import corpus as C
from blyg_sync import AuthError, BlygError, norm_base

SERIES_DAYS = {1: 'questions', 2: 'concepts', 3: 'books', 4: 'side-by-side', 5: 'terms', 6: 'oracle'}
TYPES = {
    # slug: (series name, title prefix, hopper name)
    'questions': ('Open questions', 'Open question', 'Open questions'),
    'concepts': ('Concept dossiers', 'Concept dossier', 'Concept dossiers'),
    'books': ('Book companions', 'Book companion', 'Book companions'),
    'side-by-side': ('Side by side', 'Side by side', 'Side by side'),
    'terms': ('Term watch', 'Term watch', 'Term watch'),
    'oracle': ('Oracle casts', 'Oracle cast', 'Oracle casts'),
}
TITLE_PREFIXES = {t: f'# {v[1]}: ' for t, v in TYPES.items()}

EXCLUDE_DAYS = 90
RUN_TK_BUDGET = 5        # blyg TK calls one run may spend (series + front-page blurb), of the token's 10 a day
MAX_SOURCES = 6          # sources per TK scope
MAX_SCOPES = 3           # scopes per post
QUOTE_WORDS = (15, 60)
FIRST_CONCEPT = 'legibility'
ORACLE_URL = 'https://divinations.worldmachines.org'
ICHING_PATH = F.REPO / 'tools' / 'blyg-series' / 'iching.json'
SCAN_ITEMS = 80          # recent items read to find today's post or an unfinished one

NO_INVENTION = "Use only what the notes say, and don't invent claims."
PLAIN = 'No headings, lists, links or quotations longer than a phrase.'

log = F.log


# ---------------------------------------------------------------- the published text of a note

LINK_LABEL = re.compile(r'(?<!!)\[\[([0-9a-z]{26})(?:[ \t]*\|[ \t]*([^\n\]]*))?\]\]')
HEADING = re.compile(r'^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$')
# Anything that starts a block other than a paragraph, or interrupts one.
BLOCK_START = re.compile(r'^\s{0,3}(?:[-+*](?:\s|$)|\d{1,9}[.)](?:\s|$)|>|#{1,6}(?:\s|$)|`{3,}|~{3,}|<|[-*_=]{3,}\s*$|=+\s*$)'
                         r'|^(?: {4}|\t)')
INTERRUPT = re.compile(r'^\s{0,3}(?:[-+*]\s|1[.)]\s|>|#{1,6}(?:\s|$)|`{3,}|~{3,}|<|[-*_=]{3,}\s*$|=+\s*$)|\|')
BAD_CHARS = set('[]*_`<>&\\|~#$^{}@=\x00')
OPEN_HEADING = re.compile(r'^open(?: questions?| problems?| tensions?)?\b(?!ai)', re.I)
DEFINITION_HEADING = re.compile(r'definition|the idea|what it is|core claim|in brief|summary', re.I)
ABBREV = re.compile(r'(?:\b(?:Mr|Mrs|Ms|Dr|St|Prof|vs|cf|ch|vol|pp|p|c|ca|e\.g|i\.e|etc|al|No|Fig)\.|\b[A-Z]\.)$')


@dataclass
class Sentence:
    text: str
    note: object
    section: str
    links: frozenset      # blyg ids linked inside the sentence
    para: int             # paragraph index in the note
    last: bool            # in the note's last plain paragraph
    slug: bool = False    # carries a file slug ("clark-revolutionary-spring"): verbatim, but reads badly

    @property
    def words(self):
        return len(self.text.split())


def quotable(text, lo=QUOTE_WORDS[0], hi=QUOTE_WORDS[1]):
    """A sentence Studio will find verbatim in the note's text content, and that reads as a quote."""
    n = len(text.split())
    if not lo <= n <= hi or any(ch in BAD_CHARS for ch in text) or 'http' in text or 'www.' in text:
        return False
    if not re.match(r'''^["“‘'(]?[A-Za-z]''', text):
        return False
    if not re.search(r'''[.!?]["”’')]*$''', text):
        return False
    if text.count('(') != text.count(')') or text.count('"') % 2:
        return False
    return True


META = re.compile(r'^(?:this|these|the present) (?:note|notes|section|essay|post|page|file|entry)\b|^answer\b'
                  r'|\b(?:developed for|working synthesis|draws on|drawn from|source notes?|see also|reading notes?)\b',
                  re.I)
SLUG = re.compile(r'\b[a-z0-9]+(?:-[a-z0-9]+){3,}\b|\b(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+){2,}\b')


def worth_quoting(text):
    """Quality, not safety: no notes about the notes."""
    return not META.search(text)


def split_sentences(text):
    """[(start, end)] of the sentences of one collapsed paragraph."""
    spans, start = [], 0
    for m in re.finditer(r'''[.!?]["”’')]*(?=\s+["“‘'(]?[A-Z0-9])''', text):
        if ABBREV.search(text[start:m.start() + 1]):
            continue
        spans.append((start, m.end()))
        start = m.end()
        while start < len(text) and text[start] == ' ':
            start += 1
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def paragraph_lines(lines):
    """The lines of a block that form its leading paragraph, cut at a hard break or an interrupting line."""
    if not lines or BLOCK_START.match(lines[0]):
        return []
    out = []
    for i, line in enumerate(lines):
        if i and INTERRUPT.search(line):
            break
        out.append(line)
        if re.search(r'(?: {2,}|\\)$', line):   # a hard break: Studio's text has a line break here
            break
    return out


class Texts:
    """Each note's text as the blyg holds it, and its quotable sentences."""

    def __init__(self, corpus, max_chars=100000):
        self.corpus = corpus
        self.renderer = C.Renderer(corpus.index, C.units_by_note(C.make_units(corpus.notes, max_chars)))
        self.by_id = {e['id']: p for p, e in corpus.state.items() if e.get('published_version') and '#part-' not in p}
        self._sentences = {}
        self._rendered = {}

    def _pub_id(self, key):
        e = self.corpus.state.get(key)
        return e['id'] if e and e.get('published_version') else None

    def rendered(self, note):
        """Part 1 of the note as published, or None when the repo's text no longer matches what was published."""
        if note.path in self._rendered:
            return self._rendered[note.path]
        out = None
        entry = self.corpus.state.get(note.path)
        units = self.renderer.units_by_note.get(note.path) or []
        if entry and entry.get('published_version') and units:
            md = self.renderer.render(units[0], C.render_byline(self.corpus.authors.author_for(note)), self._pub_id)
            sha = entry.get('published_sha')
            out = md if not sha or sha == C.sha(md) else None
        self._rendered[note.path] = out
        return out

    def sentences(self, note, slugs=False):
        """Quotable sentences; with `slugs`, also those that carry a file slug (book citations mostly do)."""
        out = self._all_sentences(note)
        return out if slugs else [s for s in out if not s.slug]

    def _all_sentences(self, note):
        if note.path in self._sentences:
            return self._sentences[note.path]
        md = self.rendered(note)
        out = []
        if md:
            section, paras = '', []
            for block in C._blocks(md):
                lines = block.split('\n')
                h = HEADING.match(lines[0])
                if h and len(lines) == 1:
                    section = re.sub(r'[*_`]', '', h.group(2)).strip()
                    continue
                if all(re.match(r'^\s{0,3}>', ln) for ln in lines):
                    inner = [re.sub(r'^\s{0,3}>\s?', '', ln) for ln in lines]
                    if any(re.match(r'^\s{0,3}>', ln) for ln in inner):
                        continue
                    groups, cur = [], []
                    for ln in inner:   # "> " alone is a paragraph break inside the quote
                        if ln.strip():
                            cur.append(ln)
                        elif cur:
                            groups.append(cur)
                            cur = []
                    if cur:
                        groups.append(cur)
                    for g in groups:
                        paras.append((section, paragraph_lines(g)))
                    continue
                paras.append((section, paragraph_lines(lines)))
            # The importer's footer ("**Connects:** …") is not the note's closing paragraph.
            plain_idx = [i for i, (_, ls) in enumerate(paras) if ls and not re.match(r'^\*\*[^*\n]+:\*\*', ls[0])]
            last = plain_idx[-1] if plain_idx else -1
            for i, (sec, ls) in enumerate(paras):
                if not ls:
                    continue
                text, links = self._paragraph_text(' '.join(ls))
                for s, e in split_sentences(text):
                    sent = text[s:e].strip()
                    if not quotable(sent) or not worth_quoting(sent):
                        continue
                    assert sent in text   # the quote is verbatim paragraph text, by construction
                    inside = [(a, b, i_) for (a, b, i_) in links if a >= s and b <= e]
                    ids = frozenset(i_ for (_, _, i_) in inside)
                    sluggy = bool(SLUG.search(sent)) or any(
                        re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', text[a:b]) for (a, b, _) in inside)
                    out.append(Sentence(sent, note, sec, ids, i, i == last, sluggy))
        self._sentences[note.path] = out
        return out

    @staticmethod
    def _paragraph_text(raw):
        """Collapsed paragraph text with each labelled blyg link as its label; [(start, end, id)] of the labels."""
        raw = re.sub(r'\s+', ' ', raw).strip()
        out, links, last = [], [], 0
        for m in LINK_LABEL.finditer(raw):
            out.append(raw[last:m.start()])
            lab = (m.group(2) or '').strip()
            pos = sum(len(x) for x in out)
            if lab and not any(ch in BAD_CHARS for ch in lab):
                out.append(lab)
                links.append((pos, pos + len(lab), m.group(1)))
            else:
                out.append('\x00')   # an unlabelled link reads as its target's heading: never quoted
            last = m.end()
        out.append(raw[last:])
        text = ''.join(out)
        if '[[' in text:
            text = text.replace('[[', '\x00')
        return text, links

    def links_to(self, sentence, path):
        return any(self.by_id.get(i) == path for i in sentence.links)


# ---------------------------------------------------------------- shared helpers

def series_for(day):
    return SERIES_DAYS.get(day.weekday())


def series_rng(stype, day):
    return random.Random(f'wm-series:{stype}:{day.isoformat()}')


def recent_subjects(history, stype, today, days=EXCLUDE_DAYS):
    """Subjects (and their titles, lowercased) of this series within `days` before today."""
    cutoff = today - timedelta(days=days)
    out = set()
    for d, entry in (history.get('days') or {}).items():
        s = entry.get('series') if isinstance(entry, dict) else None
        if not s or s.get('type') != stype:
            continue
        try:
            when = date.fromisoformat(d)
        except ValueError:
            continue
        if cutoff <= when <= today:
            for k in ('subject', 'subject_title'):
                if s.get(k):
                    out.add(str(s[k]).lower() if k == 'subject_title' else s[k])
    return out


def last_author(history, stype, today):
    days = sorted(d for d, e in (history.get('days') or {}).items()
                  if d < today.isoformat() and isinstance(e, dict) and (e.get('series') or {}).get('type') == stype)
    return history['days'][days[-1]]['series'].get('author') if days else None


def short_title(note):
    """A note's title for a post heading: no "(part 3 of 6)" suffix, no brackets."""
    return F.label(F.PART_TITLE.sub('', note.title).strip() or note.title)


def join_names(names):
    names = [n for n in names if n]
    if len(names) <= 1:
        return ''.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def unique(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def scope(instruction, source_ids):
    """A TK generation scope. No brackets in the instruction; at most MAX_SOURCES sources."""
    assert 0 < len(source_ids) <= MAX_SOURCES, source_ids
    text = re.sub(r'[\[\]@]', '', instruction)
    text = re.sub(r'\s+', ' ', text).strip()
    return f'[TK]{text} ' + ' '.join(f'![[{i}]]' for i in source_ids) + '[/TK]'


def partial_quote(item_id, sentence):
    """`![[id]]` with its attached quote. Studio checks the quote is in the target's text."""
    assert quotable(sentence), sentence
    return f'![[{item_id}]]\n> {sentence}'


@dataclass
class Post:
    type: str
    title: str                  # without the leading '# '
    markdown: str
    teaser: str
    subject: str
    subject_title: str
    sources: list               # note paths (and member post ids) the post draws on
    author: str = None          # author key of the post's main voice, for spreading across weeks
    scopes: int = 0             # TK generation scopes (blyg AI calls)
    quotes: dict = field(default_factory=dict)   # quoted item id → path
    note: str = ''              # extra log line


class Builder:
    """What every series shares: the corpus, the day, credits, links and quotes."""

    def __init__(self, corpus, texts, *, site, today, history, contacts=(), member_posts=(), ai=None, dry_run=False):
        self.c = corpus
        self.t = texts
        self.site = norm_base(site)
        self.today = today
        self.history = history
        self.contacts = list(contacts)
        self.member_posts = list(member_posts)
        self.ai = ai
        self.dry_run = dry_run
        self.ai_calls = 0
        self._index = None

    def sentence_index(self):
        if self._index is None:
            self._index = SentenceIndex(self)
        return self._index

    # -- people
    def name(self, note):
        return self.c.author(note)

    def handle_for(self, name):
        """`@handle` for a member the blyg's address book knows, else None."""
        if not name:
            return None
        blyg = next((a.get('blyg') for a in self.c.authors.authors.values() if a.get('name') == name), None)
        for ct in self.contacts:
            h = ct.get('handle') or ''
            if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$', h):
                continue
            if (ct.get('name') or '').strip().casefold() == name.casefold():
                return '@' + h
            if blyg and ct.get('url') and norm_base(ct['url']) == norm_base(blyg):
                return '@' + h
        return None

    def person(self, note):
        """How the post names a note's author in its own prose: @handle if known, else the plain name."""
        name = self.name(note)
        return self.handle_for(name) or name

    def credit(self, note):
        """For model instructions: always the plain name, never a handle."""
        name = self.name(note)
        if name:
            return f'"{F.label(note.title, 80)}" by {name}'
        return f'"{F.label(note.title, 80)}" ({self.c.context(note)})'

    # -- links and quotes
    def id(self, note):
        return self.c.item_id(note.path)

    def link(self, note, text=None):
        return F.link(self.id(note), text or note.title)

    def attribution(self, note):
        who = self.person(note)
        if who:
            return f'— {who}, in {self.link(note)}'
        return f'— {self.link(note)} ({F.label(self.c.context(note), 80)})'

    def quote_block(self, sentence, post_quotes):
        note = sentence.note
        post_quotes[self.id(note)] = note.path
        return f'{partial_quote(self.id(note), sentence.text)}\n\n{self.attribution(note)}'

    def series_line(self, stype):
        name = TYPES[stype][0]
        return (f'*{name} · {self.today:%A} {self.today.isoformat()} · a weekly series on the World Machines blyg. '
                f'[Every post in the series]({self.site}h/{stype}/)*')

    def quotable_note(self, note):
        """Published whole (not split into parts) and unchanged since: its sentences can be quoted."""
        return bool(self.id(note)) and f'{note.path}#part-2' not in self.c.state and self.t.rendered(note) is not None

    def spread(self, notes, limit, per_member=1, per_commons=2):
        """Round-robin by author, at most per_member each (commons per_commons), in the given order."""
        queues, order = {}, []
        for n in notes:
            k = self.c.author_key(n)
            if k not in queues:
                queues[k] = []
                order.append(k)
            queues[k].append(n)
        out, used = [], {}
        while len(out) < limit and any(queues[k] for k in order):
            for k in order:
                cap = per_commons if k == F.COMMONS else per_member
                if queues[k] and used.get(k, 0) < cap and len(out) < limit:
                    out.append(queues[k].pop(0))
                    used[k] = used.get(k, 0) + 1
                elif queues[k] and used.get(k, 0) >= cap:
                    queues[k] = []
        return out

    def score_order(self, notes):
        return sorted(notes, key=lambda n: (-self.c.score(n), n.path))

    def mention_re(self, term):
        words = [re.escape(w) for w in term.split()]
        if not words:
            return None
        body = r'\s+'.join(words)
        return re.compile(rf"(?<![\w-]){body}(?:s|es)?(?![\w-])", re.I)

    def matching_posts(self, term, limit=2):
        rx = self.mention_re(term)
        out = []
        for p in self.member_posts:
            if rx and rx.search(p.get('text') or ''):
                out.append(p)
            if len(out) >= limit:
                break
        return out

    def eligible_note(self, note):
        """Notes the series may link or use as a source."""
        if not self.id(note):
            return False
        stem = note.stem.lower()
        return stem not in ('index', 'readme', 'log') and not stem.startswith('_') and \
            self.c.area(note) not in ('wiki', 'top', 'commons')


# ---------------------------------------------------------------- B. open questions

def question_of(b, note):
    """The question a note leaves open: from its "Open" section, else a question-shaped closing line."""
    if not b.quotable_note(note):
        return None
    sents = b.t.sentences(note)
    open_s = [s for s in sents if OPEN_HEADING.match(s.section or '')]
    asked = [s for s in open_s if s.text.rstrip('"”’\')').endswith('?')]
    if asked:
        return asked[0]
    if open_s:
        return open_s[0]
    closing = [s for s in sents if s.last and s.text.rstrip('"”’\')').endswith('?')]
    return closing[-1] if closing else None


def question_pool(b):
    """{path: Sentence} for every member note with an open question."""
    pool = {}
    for n in b.c.notes:
        if b.c.author_key(n) == F.COMMONS or not b.eligible_note(n):
            continue
        q = question_of(b, n)
        if q:
            pool[n.path] = q
    return pool


def pick_by_author(b, notes, rng, avoid=None):
    """Author-first: an author uniformly (not `avoid` when anyone else is left), then a score-weighted note."""
    queues = F.by_author(b.c, list(notes), rng)
    if not queues:
        return None
    authors = sorted(queues)
    if avoid in authors and len(authors) > 1:
        authors.remove(avoid)
    return queues[rng.choice(authors)][0]


STOP = set('''about above after again against almost along already also although always among another
any anything are around because been before being below between both but cannot could does doing down
during each either else enough even ever every from further have having here hers herself himself however
into itself just least less like made make makes many might more most much must neither never nothing
often once only other others ought ours ourselves over own perhaps rather same should since some something
such than that their theirs them themselves then there these they thing things this those though through
thus together under until upon very what whatever when where whether which while whom whose will with
within without would your yours yourself yourselves question open note notes world machine machines
whether still actually really might become becomes'''.split())


def terms_of(text):
    return {w for w in re.findall(r"[a-z][a-z'-]{4,}", text.lower()) if w not in STOP}


class TermIndex:
    def __init__(self, b):
        self.b = b
        self._terms = {}

    def terms(self, note):
        if note.path not in self._terms:
            summary = note.front.get('summary') if isinstance(note.front.get('summary'), str) else ''
            self._terms[note.path] = terms_of(f'{note.title} {summary} {self.b.c.plain(note)[:3000]}')
        return self._terms[note.path]


def neighbours(c, note):
    return set(c.outbound.get(note.path, ())) | {p for p, ts in c.outbound.items() if note.path in ts}


def related_notes(b, note, question, limit=6):
    c = b.c
    near = neighbours(c, note)
    want = terms_of(question.text) | terms_of(note.title)
    idx = TermIndex(b)
    scored = []
    for n in c.notes:
        if n is note or not b.eligible_note(n):
            continue
        shared = len(want & idx.terms(n)) if want else 0
        graph = n.path in near
        if not graph and shared < 2:
            continue
        s = (3 if graph else 0) + shared + (1 if c.author_key(n) != F.COMMONS else 0) + 0.1 * c.score(n)
        scored.append((s, n))
    scored.sort(key=lambda sn: (-sn[0], sn[1].path))
    return b.spread([n for _, n in scored], limit, per_member=2, per_commons=2)


def build_questions(b):
    stype = 'questions'
    recent = recent_subjects(b.history, stype, b.today)
    pool = {p: q for p, q in question_pool(b).items() if p not in recent}
    if not pool:
        return None
    rng = series_rng(stype, b.today)
    note = pick_by_author(b, [b.c.by_path[p] for p in pool], rng, last_author(b.history, stype, b.today))
    q = pool[note.path]
    related = related_notes(b, note, q)
    quotes = {}
    sources = [note] + related[:MAX_SOURCES - 1]
    lines = [
        f'# {TYPES[stype][1]}: {short_title(note)}', '',
        b.series_line(stype), '',
        f'Every Tuesday the blyg takes one question a member has left open in their notes and gathers the notes that '
        f'bear on it. This week\'s comes from {b.person(note)}, in {b.link(note)}.', '',
        b.quote_block(q, quotes), '',
    ]
    if related:
        lines += ['## Notes that bear on it', '']
        lines += [f'- {b.link(n)} · *{F.label(b.c.context(n), 100)}*' for n in related]
        lines += ['', '## How they bear on it', '']
        instr = (
            f'An open question from {b.credit(note)}: {q.text} '
            f'Below are that note and {len(sources) - 1} other notes from the World Machines group: '
            f'{"; ".join(b.credit(n) for n in sources[1:])}. '
            'In two or three short paragraphs of plain prose, say which of these notes bear on the question and how: '
            'what each relevant note offers toward an answer, and where they point in different directions. '
            'Credit each idea to its author by name; notes without a named author are the group\'s shared notes. '
            f'Say plainly when a note does not bear on it. {NO_INVENTION} {PLAIN}'
        )
        lines += [scope(instr, [b.id(n) for n in sources]), '']
    teaser = (f'{b.name(note) or "A member"} left a question open in "{F.label(note.title)}": '
              f'"{F.clip(q.text, 300)}" Today\'s post gathers {len(related)} notes that bear on it.')
    return Post(stype, f'{TYPES[stype][1]}: {short_title(note)}', '\n'.join(lines).rstrip() + '\n', teaser,
                note.path, note.title, [n.path for n in [note] + related], b.c.author_key(note),
                scopes=1 if related else 0, quotes=quotes, note=f'question: {q.text}')


# ---------------------------------------------------------------- A. concept dossier

def concept_candidates(b):
    out = []
    for n in b.c.notes:
        if not b.eligible_note(n):
            continue
        p = n.path
        if '/concepts/' in p or p.startswith('raw-notes/commons/glossary/') or '/synthesis/' in p:
            out.append(n)
    return out


def definition_of(b, note):
    sents = b.t.sentences(note)
    for s in sents:
        if DEFINITION_HEADING.search(s.section or ''):
            return s
    return sents[0] if sents else None


def usage_sentence(b, user, concept):
    """The sentence in `user` that uses `concept`: one linking it, else one naming it."""
    sents = b.t.sentences(user)
    linked = [s for s in sents if b.t.links_to(s, concept.path)]
    if linked:
        return linked[0]
    rx = b.mention_re(re.sub(r'\s*\(.*?\)\s*', ' ', concept.title).strip())
    named = [s for s in sents if rx and rx.search(s.text)]
    return named[0] if named else None


def concept_term(note):
    return re.sub(r'\s*\(.*?\)\s*', ' ', note.title).strip()


def concept_uses(b, concept):
    """{path: Sentence} of the notes that use a concept: a sentence linking its note, else one naming it.

    Members often name a concept without linking its note, so naming counts as a use.
    """
    c = b.c
    uses = {}
    for p in linkers(c, concept):
        n = c.by_path[p]
        if n is concept or not b.eligible_note(n) or not b.quotable_note(n):
            continue
        s = usage_sentence(b, n, concept)
        if s:
            uses[n.path] = s
    term = concept_term(concept)
    if len(term) >= 5:
        for s in b.sentence_index().find(term):
            n = s.note
            if n is not concept and n.path not in uses and n.title.strip().lower() != concept.title.strip().lower():
                uses[n.path] = s
    return uses


def linkers(c, note):
    return sorted(p for p, ts in c.outbound.items() if note.path in ts)


def build_concepts(b):
    stype = 'concepts'
    c = b.c
    recent = recent_subjects(b.history, stype, b.today)
    ever = any((e.get('series') or {}).get('type') == stype for e in (b.history.get('days') or {}).values()
               if isinstance(e, dict))
    cands = [n for n in concept_candidates(b) if n.path not in recent and n.title.lower() not in recent]
    cands.sort(key=lambda n: (-c.inbound.get(n.path, 0), n.path))
    if not ever:
        first = [n for n in cands if n.title.strip().lower() == FIRST_CONCEPT]
        cands = first + [n for n in cands if n not in first]
    for concept in cands:
        post = concept_post(b, concept)
        if post:
            return post
    return None


def concept_post(b, concept):
    stype = 'concepts'
    c = b.c
    if not b.quotable_note(concept):
        return None
    definition = definition_of(b, concept)
    if not definition:
        return None
    term = concept_term(concept)
    uses = concept_uses(b, concept)
    users = [c.by_path[p] for p in uses]
    members = [n for n in users if c.author_key(n) != F.COMMONS]
    ordered = b.score_order(members) + b.score_order([n for n in users if c.author_key(n) == F.COMMONS])
    quoted = b.spread(ordered, MAX_SOURCES - 1)
    if len(quoted) < 2:
        return None
    quotes = {}
    title = F.label(concept.title)
    remote = b.matching_posts(term)
    lines = [
        f'# {TYPES[stype][1]}: {title}', '',
        b.series_line(stype), '',
        f'Every Wednesday the blyg takes one concept from the notes and shows how members use it. '
        f'This week: {b.link(concept)}.', '',
        '## The definition', '',
        f'{partial_quote(b.id(concept), definition.text)}', '',
        b.attribution(concept), '',
        '## How members use it', '',
    ]
    quotes[b.id(concept)] = concept.path
    for n in quoted:
        lines += [b.quote_block(uses[n.path], quotes), '']
    lines += ['## Where the uses agree and diverge', '']
    sources = [concept] + quoted
    instr = (
        f'These notes from the World Machines group all use the concept "{F.label(term, 80)}". The first is the '
        f'concept note itself, {b.credit(concept)}; the others are {"; ".join(b.credit(n) for n in quoted)}. '
        'In two or three short paragraphs of plain prose, say where their uses of the concept agree and where they '
        'diverge: what each note takes the concept to be for, and what it adds. Credit each use to its author by name. '
        'If the uses agree, say so plainly; never invent a disagreement. '
        f'{NO_INVENTION} {PLAIN}'
    )
    lines += [scope(instr, [b.id(n) for n in sources]), '']
    scopes = 1
    if remote:
        lines += ["## On members' own blygs", '']
        lines += [f"- {F.link(p['remoteId'], p['title'])} — {F.label(p['author'], 60)}" for p in remote]
        instr2 = (
            f'The first source is the World Machines concept note on "{F.label(term, 80)}". The others are recent '
            f'posts by members on their own blygs: {"; ".join(chr(34) + F.label(p["title"], 80) + chr(34) + " by " + F.label(p["author"], 60) for p in remote)}. '
            'In one short paragraph of plain prose, say how these posts use the concept compared with the note, '
            'crediting each post to its author by name. Say plainly when they agree. '
            "Use only what the sources say, and don't invent claims. " + PLAIN
        )
        lines += ['', scope(instr2, [b.id(concept)] + [p['remoteId'] for p in remote]), '']
        scopes += 1
    quoted_paths = {n.path for n in quoted}
    others = [c.by_path[p] for p in linkers(c, concept)
              if p not in quoted_paths and b.eligible_note(c.by_path[p]) and c.by_path[p] is not concept]
    others += [n for n in users if n.path not in quoted_paths and n not in others]
    members_first = lambda ns: b.score_order([n for n in ns if c.author_key(n) != F.COMMONS]) + \
        b.score_order([n for n in ns if c.author_key(n) == F.COMMONS])
    others = members_first(others)
    if others:
        shown = others[:20]
        more = f' · and {len(others) - len(shown)} more' if len(others) > len(shown) else ''
        lines += ['## Other notes that mention it', '', ' · '.join(b.link(n) for n in shown) + more, '']
    names = join_names(unique(b.name(n) or 'the shared notes' for n in quoted))
    teaser = (f'What the group means by {title}: the concept note\'s own definition, how {len(quoted)} notes by '
              f'{names} use it, and a machine-written reading of where those uses agree and diverge.')
    return Post(stype, f'{TYPES[stype][1]}: {title}', '\n'.join(lines).rstrip() + '\n', teaser, concept.path,
                concept.title, [n.path for n in sources] + [p['remoteId'] for p in remote],
                c.author_key(concept), scopes=scopes, quotes=quotes)


# ---------------------------------------------------------------- C. book companion

def book_notes(c, slug):
    return sorted((n for n in c.notes if c.book_slug(n) == slug and c.item_id(n.path)), key=lambda n: n.path)


def book_citers(b, slug):
    """Notes outside the reading notes that link into this book's notes (summary included)."""
    c = b.c
    targets = {n.path for n in book_notes(c, slug)}
    summary = c.book_summary(slug)
    if summary:
        targets.add(summary.path)
    out = []
    for p, ts in c.outbound.items():
        n = c.by_path[p]
        if p in targets or c.area(n) == 'reading' or not b.eligible_note(n):
            continue
        hit = ts & targets
        if hit:
            out.append((n, hit))
    return out


def cite_sentence(b, note, hit, title):
    """The sentence in `note` that links into the book (`hit`: its notes' paths), else one naming its title."""
    # Citations mostly name the book by its slug ("Clark's clark-revolutionary-spring"): allowed here, after
    # sentences without one, but never a chapter id in parentheses ("(morley-diderot-v2-ch04-...)").
    ss = [s for s in b.t.sentences(note, slugs=True) if not SLUG.search(s.text)]
    ss.sort(key=lambda s: s.slug)
    s = next((s for s in ss if any(b.t.by_id.get(i) in hit for i in s.links)), None)
    rx = b.mention_re(title) if len(title.split()) >= 2 else None   # one word ("Utopia") matches too much
    if s is None and rx:
        s = next((s for s in ss if rx.search(s.text)), None)
    return s


def build_books(b):
    stype = 'books'
    c = b.c
    recent = recent_subjects(b.history, stype, b.today)
    ranked = []
    for slug, title, path in c.books():
        if slug in recent:
            continue
        citers = book_citers(b, slug)
        # Most cited from outside the reading notes first; a book some citing note can be quoted from goes ahead.
        quotable = any(cite_sentence(b, n, hit, title) for n, hit in citers if b.quotable_note(n))
        ranked.append((not quotable, -len(citers), slug, title, path, citers))
    ranked.sort(key=lambda r: r[:3])
    for _, _, slug, title, path, citers in ranked:
        post = book_post(b, slug, title, path, citers)
        if post:
            return post
    return None


def book_post(b, slug, title, path, citers):
    stype = 'books'
    c = b.c
    summary = c.book_summary(slug)
    summary = summary if summary and c.item_id(summary.path) else None
    chapters = book_notes(c, slug)
    if not summary and not chapters:
        return None
    quotes, quoted, sents = {}, [], {}
    for n, hit in citers:
        if not b.quotable_note(n):
            continue
        s = cite_sentence(b, n, hit, title)
        if s:
            sents[n.path] = s
            quoted.append(n)
    members = [n for n in quoted if c.author_key(n) != F.COMMONS]
    quoted = b.spread(b.score_order(members) + b.score_order([n for n in quoted if n not in members]),
                      MAX_SOURCES - 1)
    head = summary or chapters[0]
    lines = [
        f'# {TYPES[stype][1]}: {F.label(title)}', '',
        b.series_line(stype), '',
        f'Every Thursday the blyg opens one book the group has read. This week: *{F.label(title)}*. '
        + (f'Start with the summary, {b.link(summary)}.' if summary else f'Start with the first chapter note, {b.link(head)}.'),
        '',
    ]
    if chapters:
        lines += [f'## The chapter notes ({len(chapters)})', '']
        lines += [f'- {b.link(n)}' for n in chapters[:60]]
        if len(chapters) > 60:
            lines.append(f'- …and {len(chapters) - 60} more in the book\'s reading notes')
        lines.append('')
    if quoted:
        lines += ['## Where the notes cite it', '']
        for n in quoted:
            lines += [b.quote_block(sents[n.path], quotes), '']
    lines += ['## What the group has taken from it so far', '']
    sources = [head] + (quoted if quoted else [n for n in chapters if n is not head][:MAX_SOURCES - 1])
    who = '; '.join(b.credit(n) for n in sources[1:])
    instr = (
        f'The first source is the World Machines group\'s {"summary" if summary else "first reading note"} of the book '
        f'"{F.label(title, 80)}". The others are {"notes that cite it" if quoted else "more of its reading notes"}: {who}. '
        'In two or three short paragraphs of plain prose, say what the group has taken from this book so far: '
        'which of its ideas the notes pick up, what they use them for, and what they leave aside. '
        f'Credit each idea to its author by name. {NO_INVENTION} {PLAIN}'
    )
    lines += [scope(instr, [b.id(n) for n in sources]), '']
    names = join_names(unique(b.name(n) or 'the shared notes' for n in quoted))
    teaser = (f'A companion to {F.label(title)}: ' + ('its summary, ' if summary else '') +
              f'{len(chapters)} chapter notes' +
              (f', and what {len(quoted)} notes by {names} have taken from it.' if quoted else
               ', and a machine-written note on what the group has taken from it so far.'))
    return Post(stype, f'{TYPES[stype][1]}: {F.label(title)}', '\n'.join(lines).rstrip() + '\n', teaser, slug,
                title, [n.path for n in sources], None, scopes=1, quotes=quotes)


# ---------------------------------------------------------------- D. side by side

def build_side_by_side(b):
    stype = 'side-by-side'
    c = b.c
    recent = recent_subjects(b.history, stype, b.today)
    used = set()
    cutoff = b.today - timedelta(days=EXCLUDE_DAYS)
    for d, e in (b.history.get('days') or {}).items():
        s = (e or {}).get('series') or {}
        if s.get('type') == stype and d >= cutoff.isoformat():
            used.update(s.get('sources') or [])
    options = []   # (concept, {author: [(note, sentence)]})
    targets = {n.path: n for n in concept_candidates(b)}
    for n in c.notes:   # and any much-linked note that is not a reading note, a summary or a person
        if c.inbound.get(n.path, 0) >= 5 and b.eligible_note(n) and c.area(n) not in ('reading', 'summaries', 'entities'):
            targets.setdefault(n.path, n)
    for target in sorted(targets.values(), key=lambda n: n.path):
        if target.path in recent:
            continue
        by = {}
        for p, s in concept_uses(b, target).items():
            if p not in used:
                by.setdefault(c.author_key(c.by_path[p]), []).append((c.by_path[p], s))
        if len(by) >= 2:
            options.append((target, by))
    if not options:
        return None
    rng = series_rng(stype, b.today)
    pairs = [o for o in options if sum(1 for a in o[1] if a != F.COMMONS) >= 2] or options
    target, by = rng.choice(pairs)
    authors = sorted(a for a in by if a != F.COMMONS) if sum(1 for a in by if a != F.COMMONS) >= 2 else sorted(by)
    two = rng.sample(authors, 2)
    picks = []
    for a in two:
        n, s = sorted(by[a], key=lambda ns: (-c.score(ns[0]), ns[0].path))[0]
        picks.append((n, s))
    (na, sa), (nb, sb) = picks
    quotes = {}
    concept = F.label(target.title)
    who_a, who_b = b.name(na) or 'the shared notes', b.name(nb) or 'the shared notes'
    lines = [
        f'# {TYPES[stype][1]}: {who_a} and {who_b} on {concept}', '',
        b.series_line(stype), '',
        f'Every Friday the blyg sets two notes by different authors side by side. This week both draw on '
        f'{b.link(target)}.', '',
        b.quote_block(sa, quotes), '',
        b.quote_block(sb, quotes), '',
        '## Read together', '',
        scope(
            f'Two notes by different members of the World Machines group both draw on the idea of "{concept}": '
            f'{b.credit(na)} and {b.credit(nb)}. In one or two short paragraphs of plain prose, compare what each '
            'says about it and what each uses it for. If they agree, say plainly that they agree; never invent a '
            'disagreement, and do not inflate a difference of emphasis into a conflict. Credit each point to its '
            f'author by name. {NO_INVENTION} {PLAIN}',
            [b.id(na), b.id(nb)]), '',
    ]
    teaser = (f'{who_a} and {who_b} both lean on {concept}. Today\'s post sets their notes, '
              f'"{F.label(na.title)}" and "{F.label(nb.title)}", side by side.')
    return Post(stype, f'{TYPES[stype][1]}: {who_a} and {who_b} on {concept}', '\n'.join(lines).rstrip() + '\n',
                teaser, target.path, target.title, [na.path, nb.path], None, scopes=1, quotes=quotes)


# ---------------------------------------------------------------- E. term watch

def term_candidates(b):
    """{term (lowercase): defining note or None}: glossary and concept titles, and frequently linked targets."""
    c = b.c
    out = {}
    for n in c.notes:
        if not b.eligible_note(n):
            continue
        p = n.path
        concept = '/concepts/' in p or p.startswith('raw-notes/commons/glossary/')
        linked = c.inbound.get(p, 0) >= 5 and c.area(n) not in ('reading', 'entities', 'summaries')
        if not (concept or linked):
            continue
        t = re.sub(r'\s*\(.*?\)\s*', ' ', n.title)
        t = re.sub(r'[^\w\s\'-]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip().lower()
        if not t or len(t.split()) > 3 or len(t) < 5 or t in STOP:
            continue
        if t not in out or p.startswith('raw-notes/commons/glossary/'):
            out[t] = n
    return out


def stem(w):
    return w[:-2] if w.endswith('es') and len(w) > 5 else w[:-1] if w.endswith('s') and len(w) > 4 else w


class SentenceIndex:
    def __init__(self, b):
        self.b = b
        self.posting = {}
        self.all = []
        for n in b.c.notes:
            if not b.eligible_note(n) or not b.quotable_note(n):
                continue
            for s in b.t.sentences(n):
                k = len(self.all)
                self.all.append(s)
                for w in {stem(w) for w in re.findall(r"[a-z0-9']+", s.text.lower())}:
                    self.posting.setdefault(w, []).append(k)

    def find(self, term):
        words = [stem(w) for w in re.findall(r"[a-z0-9']+", term.lower())]
        if not words:
            return []
        sets = [set(self.posting.get(w, ())) for w in words]
        hits = set.intersection(*sets) if sets else set()
        rx = self.b.mention_re(term)
        return [self.all[k] for k in sorted(hits) if rx.search(self.all[k].text)]


def build_terms(b):
    stype = 'terms'
    c = b.c
    recent = recent_subjects(b.history, stype, b.today)
    cands = {t: n for t, n in term_candidates(b).items() if t not in recent}
    if not cands:
        return None
    idx = SentenceIndex(b)
    options = []
    for term in sorted(cands):
        home = cands[term]
        by = {}
        for s in idx.find(term):
            if s.note is home:
                continue
            by.setdefault(c.author_key(s.note), []).append(s)
        if len(by) >= 2:
            options.append((term, home, by))
    if not options:
        return None
    rng = series_rng(stype, b.today)
    multi = [o for o in options if sum(1 for a in o[2] if a != F.COMMONS) >= 2]
    pool = multi or options
    weights = [len(o[2]) for o in pool]
    term, home, by = rng.choices(pool, weights=weights, k=1)[0]
    picks = []
    for a in sorted(by):
        per_note = {}
        for s in by[a]:
            per_note.setdefault(s.note.path, s)
        notes = sorted(per_note.values(), key=lambda s: s.note.path)
        rng.shuffle(notes)
        picks.append((a, notes))
    rng.shuffle(picks)
    picks.sort(key=lambda an: an[0] == F.COMMONS)   # members first, commons last
    chosen = []
    for a, ss in picks:
        cap = 2 if a == F.COMMONS else 1
        chosen += ss[:cap]
    chosen = chosen[:MAX_SOURCES]
    quotes = {}
    shown = F.label(term)
    glossary = next((n for n in c.notes if n.path.startswith('raw-notes/commons/glossary/')
                     and n.title.strip().lower() == term and c.item_id(n.path)), None)
    remote = b.matching_posts(term, limit=MAX_SOURCES - len(chosen))
    lines = [
        f'# {TYPES[stype][1]}: {shown}', '',
        b.series_line(stype), '',
        f'Every Saturday the blyg follows one term through the notes of different members. This week: "{shown}"'
        + (f', which the glossary defines in {b.link(glossary)}.' if glossary else
           f', which has its own note, {b.link(home)}.' if home is not None and c.item_id(home.path) else '.'),
        '',
        '## Where it turns up', '',
    ]
    for s in chosen:
        lines += [b.quote_block(s, quotes), '']
    if remote:
        lines += ["Also on members' own blygs: " + ' · '.join(
            f"{F.link(p['remoteId'], p['title'])} ({F.label(p['author'], 60)})" for p in remote), '']
    lines += ['## Do they mean the same thing?', '']
    who = '; '.join([b.credit(s.note) for s in chosen] +
                    [f'"{F.label(p["title"], 80)}" by {F.label(p["author"], 60)}' for p in remote])
    instr = (
        f'Each of these sources from the World Machines group uses the term "{shown}": {who}. '
        'In two or three short paragraphs of plain prose, say whether they mean the same thing by it. Where the '
        'meanings match, say so plainly; where they differ, say how, crediting each use to its author by name. '
        'Never invent a difference. ' + NO_INVENTION + ' ' + PLAIN
    )
    lines += [scope(instr, [b.id(s.note) for s in chosen] + [p['remoteId'] for p in remote]), '']
    names = join_names(unique(b.name(s.note) or 'the shared notes' for s in chosen))
    teaser = f'"{shown}" turns up in notes by {names}. Do they mean the same thing by it?'
    return Post(stype, f'{TYPES[stype][1]}: {shown}', '\n'.join(lines).rstrip() + '\n', teaser, term, term,
                [s.note.path for s in chosen] + [p['remoteId'] for p in remote], None, scopes=1, quotes=quotes)


# ---------------------------------------------------------------- I. oracle cast

def load_iching(path=ICHING_PATH):
    return json.loads(Path(path).read_text())


def cast_iching(rng):
    """Six three-coin throws, bottom line first: 6 changing yin, 7 yang, 8 yin, 9 changing yang (WM-Divinations)."""
    return [6 + rng.randrange(2) + rng.randrange(2) + rng.randrange(2) for _ in range(6)]


def hexagram_patterns(values):
    primary = ''.join('1' if v in (7, 9) else '0' for v in values)
    relating = ''.join('0' if v == 9 else '1' if v == 6 else ch for v, ch in zip(values, primary))
    return primary, relating


def legge_clean(text):
    return re.sub(r'\s+', ' ', re.sub(r'\[', '(', re.sub(r'\]', ')', text or ''))).strip()


def oracle_texts(iching, values):
    by = {h['pattern']: h for h in iching['hexagrams']}
    p, r = hexagram_patterns(values)
    primary, relating = by[p], by[r]
    changing = [i for i, v in enumerate(values) if v in (6, 9)]
    lines = [legge_clean(re.sub(r'^\s*\S+\.\s*', '', primary['lines'][i])) for i in changing]
    special = legge_clean(re.sub(r'^\s*\S+\.\s*', '', primary.get('allChanging') or '')) if len(changing) == 6 else ''
    return primary, relating, changing, lines, special


ORACLE_SYSTEM = (
    'You read I Ching casts for World Machines, a group building psychohistorical models of how large systems '
    'shape civilizations. A cast is chance; its old images are a prompt for thinking, never a prediction. '
    'You write plain prose only.'
)


def oracle_prompt(b, note, question, primary, relating, changing, line_texts, special):
    cast = [f'Primary hexagram {primary["number"]}, {primary["name"]}: {legge_clean(primary["judgment"])}']
    for i, t in zip(changing, line_texts):
        cast.append(f'Changing line {i + 1} (bottom = 1): {t}')
    if special:
        cast.append(f'All lines changing: {special}')
    if changing:
        cast.append(f'Relating hexagram {relating["number"]}, {relating["name"]}: {legge_clean(relating["judgment"])}')
    who = b.name(note) or 'a member'
    return '\n'.join([
        f'The question, left open by {who} in the note "{F.label(note.title)}": {question}',
        '',
        f'The note, for context: {F.clip(b.c.plain(note), 2500)}',
        '',
        'The cast (James Legge\'s translation):',
        *cast,
        '',
        'Write a reading of 150 to 250 words in two or three paragraphs separated by blank lines. Apply the images '
        'of the cast to the question as a way of thinking about it: what they suggest attending to, what they warn '
        f'against, what they leave open. Name {who} once. Do not predict events or claim the cast knows anything. '
        'No headings, lists, links, markdown, or quotations longer than a short phrase.',
    ])


def clean_reading(text):
    paras = [F.safe_generated(p) for p in re.split(r'\n\s*\n', text or '') if F.safe_generated(p)]
    paras = [re.sub(r'^(?:here is|here\'s)[^:]*:\s*', '', p, flags=re.I) for p in paras]
    if not 80 <= sum(F.words(p) for p in paras) <= 400:
        return None
    if len(paras) > MAX_SCOPES:
        paras = paras[:MAX_SCOPES - 1] + [' '.join(paras[MAX_SCOPES - 1:])]
    return paras


def build_oracle(b, iching=None):
    stype = 'oracle'
    recent = recent_subjects(b.history, stype, b.today)
    pool = {p: q for p, q in question_pool(b).items() if p not in recent}
    if not pool:
        return None
    try:
        iching = iching or load_iching()
    except (OSError, ValueError) as e:
        log(f'  ! no I Ching text ({e}); no oracle cast today')
        return None
    rng = series_rng(stype, b.today)
    note = pick_by_author(b, [b.c.by_path[p] for p in pool], rng, last_author(b.history, stype, b.today))
    q = pool[note.path]
    values = cast_iching(rng)
    primary, relating, changing, line_texts, special = oracle_texts(iching, values)
    prompt = oracle_prompt(b, note, q.text, primary, relating, changing, line_texts, special)
    paras = None
    if b.ai:
        try:
            b.ai_calls += 1
            paras = clean_reading(b.ai.chat(ORACLE_SYSTEM, prompt, max_tokens=900, temperature=0.7))
            if not paras:
                log('  ! the oracle reading was unusable')
        except F.AiError as e:
            log(f'  ! Workers AI oracle reading failed: {e}')
    if not paras:
        if not b.dry_run:
            return None
        log('  (dry run: no Workers AI reading; a placeholder stands in. The prompt would be:)')
        log(prompt)
        paras = ['(dry run) The Workers AI reading goes here: two or three paragraphs applying the cast to the question.']
    quotes = {}
    name = f'{legge_clean(primary["name"])} ({primary["number"]})'
    moves = ', '.join(str(v) for v in values)
    cast_line = (f'Six throws of three coins, read bottom to top: {moves}. That is hexagram {primary["number"]}, '
                 f'{legge_clean(primary["name"])}'
                 + (f', with {"line" if len(changing) == 1 else "lines"} {join_names([str(i + 1) for i in changing])} '
                    f'changing, which turns it into hexagram {relating["number"]}, {legge_clean(relating["name"])}.'
                    if changing else ', with no changing lines.'))
    quote = [f'> **{primary["number"]}. {legge_clean(primary["name"])}.** {legge_clean(primary["judgment"])}']
    for i, t in zip(changing, line_texts):
        quote += ['>', f'> *Line {i + 1}.* {t}']
    if special:
        quote += ['>', f'> *All lines changing.* {special}']
    if changing:
        quote += ['>', f'> **{relating["number"]}. {legge_clean(relating["name"])}.** {legge_clean(relating["judgment"])}']
    lines = [
        f'# {TYPES[stype][1]}: {name} on {short_title(note)}', '',
        b.series_line(stype), '',
        f'Every Sunday the blyg casts the I Ching for one question a member has left open, the way '
        f'[WM-Divinations]({ORACLE_URL}) does: three coins, six throws, the lines read from the bottom up. '
        'The cast is chance and the reading below is machine-written; it is a prompt for thinking, not a prediction.',
        '',
        '## The question', '',
        f'From {b.person(note)}, in {b.link(note)}.', '',
        f'{partial_quote(b.id(note), q.text)}', '',
        '## The cast', '',
        cast_line, '',
        *quote, '',
        f'*From James Legge\'s translation, The Yî King (1882), in the public domain; the text WM-Divinations uses.*',
        '',
        '## The reading', '',
    ]
    quotes[b.id(note)] = note.path
    for p in paras:
        lines += [F.impyrt(p, b.ai.model if b.ai else F.MODEL), '']
    teaser = (f'This week\'s I Ching cast is hexagram {name}, read against a question '
              f'{b.name(note) or "a member"} left open in "{F.label(note.title)}".')
    return Post(stype, f'{TYPES[stype][1]}: {name} on {short_title(note)}', '\n'.join(lines).rstrip() + '\n', teaser,
                note.path, note.title, [note.path], b.c.author_key(note), scopes=0, quotes=quotes,
                note=f'cast {values} → {primary["number"]}' + (f' → {relating["number"]}' if changing else ''))


BUILDERS = {
    'questions': build_questions, 'concepts': build_concepts, 'books': build_books,
    'side-by-side': build_side_by_side, 'terms': build_terms, 'oracle': build_oracle,
}


def check_grammar(post):
    """Raise AssertionError when the post breaks a rule Studio or this series sets."""
    md = post.markdown
    scopes = list(re.finditer(r'\[TK\](.*?)\[/TK\]', md, re.S))
    assert len(scopes) <= MAX_SCOPES, f'{len(scopes)} scopes'
    for m in scopes:
        body = m.group(1)
        if body.startswith('impyrt'):
            assert '[' not in body and ']' not in body
            continue
        instr = body.split('[=]', 1)[0]
        srcs = re.findall(r'!\[\[([0-9a-z]{26})\]\]', instr)
        assert 1 <= len(srcs) <= MAX_SOURCES, f'{len(srcs)} sources'
        assert not re.search(r'(?<!!)\[\[', instr), 'a link inside a scope'
        assert '@' not in instr, 'a handle inside a scope'
    outside = re.sub(r'\[TK\].*?\[/TK\]', '', md, flags=re.S)
    for m in re.finditer(r'^!\[\[([0-9a-z]{26})\]\]\n((?:>.*\n?)+)', outside, re.M):
        assert quotable(m.group(2)[2:].strip()), m.group(2)
    return True


# ---------------------------------------------------------------- reading the blyg

def read_contacts(api):
    if api is None:
        return []
    try:
        return (api.get('/contacts') or {}).get('contacts') or []
    except BlygError as e:
        if isinstance(e, AuthError) and e.status == 401:
            raise
        log(f'  ! could not read the address book ({e}); names stay plain')
        return []


def read_member_posts(api, slug=F.DEFAULT_SLUG, limit=60):
    """Posts filed into the members hopper, held as full imported items: [{remoteId, title, author, text}]."""
    if api is None:
        return []
    try:
        hopper = next((h for h in api.hoppers() if h.get('slug') == slug), None)
        if not hopper:
            return []
        out = []
        for m in api.memberships(hopper['id']):
            if len(out) >= limit:
                break
            it = m.get('item')
            if m.get('subscriptionId') == F.OWN_SUBSCRIPTION or not it or it.get('l0') \
                    or it.get('state', 'current') != 'current':
                continue
            author = it.get('author') if isinstance(it.get('author'), dict) else {}
            out.append({'remoteId': m['remoteId'], 'title': F.item_title(it.get('contentMd')),
                        'author': author.get('name') or 'a member', 'text': F.plain(it.get('contentMd') or '')})
        return out
    except BlygError as e:
        if isinstance(e, AuthError) and e.status == 401:
            raise
        log(f'  ! could not read member posts ({e})')
        return []


def series_line_date(md):
    m = re.search(r'^\*[^*\n]* · \w+day (\d{4}-\d{2}-\d{2}) · a weekly series', md, re.M)
    return m.group(1) if m else None


def series_type_of(md):
    for t, prefix in TITLE_PREFIXES.items():
        if (md or '').startswith(prefix):
            return t
    return None


# ---------------------------------------------------------------- writing to the blyg

class GenerationFailed(Exception):
    pass


QUOTE_DIRECTIVE = re.compile(r'^!\[\[([0-9a-z]{26})\]\]')


def drop_quote(content_md, item_id):
    """Remove a partial quote of `item_id`: the directive, its quote, and the attribution line under it."""
    pat = re.compile(rf'^!\[\[{item_id}\]\]\n(?:>[^\n]*\n?)+(?:\n(?:— [^\n]*)\n?)?\n?', re.M)
    return pat.sub('', content_md)


def pending_scopes(content_md):
    """Indexes of generation scopes with no output yet (impyrt scopes are complete)."""
    out = []
    for i, m in enumerate(re.finditer(r'\[TK\](.*?)\[/TK\]', content_md, re.S)):
        body = m.group(1)
        if not body.startswith('impyrt') and '[=]' not in body:
            out.append(i)
    return out


class Runner:
    """Builds, resumes, generates, publishes and files series posts."""

    def __init__(self, corpus, *, api=None, ai=None, site, history, today, dry_run=False, texts=None,
                 budget=RUN_TK_BUDGET, report=None):
        self.c = corpus
        self.api = api
        self.ai = ai
        self.site = norm_base(site)
        self.history = history
        self.today = today
        self.dry_run = dry_run
        self.texts = texts
        self.budget = budget
        self.report = report if report is not None else {}
        self.report.setdefault('blyg_generate_calls', 0)
        self._hoppers = None

    def builder(self):
        if self.texts is None:
            self.texts = Texts(self.c)
        contacts = read_contacts(self.api)
        members = read_member_posts(self.api)
        if self.api is not None:
            log(f'  address book: {len(contacts)} contact(s); {len(members)} member post(s) held')
        return Builder(self.c, self.texts, site=self.site, today=self.today, history=self.history,
                       contacts=contacts, member_posts=members, ai=self.ai, dry_run=self.dry_run)

    def build(self, stype):
        b = self.builder()
        post = BUILDERS[stype](b)
        if post:
            check_grammar(post)
        return post

    @property
    def spent(self):
        return self.report['blyg_generate_calls']

    # -- finding posts already on the blyg
    def recent_series_items(self):
        out = []
        for i, it in enumerate(self.api.items()):
            if i >= SCAN_ITEMS:
                break
            if series_type_of(it.get('contentMd')):
                out.append(it)
        return out

    def todays_item(self, stype, items):
        for it in items:
            if series_type_of(it.get('contentMd')) == stype and series_line_date(it.get('contentMd') or '') \
                    == self.today.isoformat() and it.get('status') in ('draft', 'public'):
                return it
        return None

    # -- the day's run
    def run_today(self, stype, reserve=0):
        """Build, publish and file today's post. Returns a result dict or None (the front page falls back)."""
        log(f'Series: {TYPES[stype][0]} ({stype}) for {self.today:%A} {self.today}')
        post = self.build(stype)
        if post is None:
            log('  no eligible subject for this series today')
            if self.api is not None and not self.dry_run:
                self.resume(self.recent_series_items(), reserve=reserve + 1)   # the featured blurb's one call
            return None
        log(f'  subject: {post.subject} — {post.title}' + (f' ({post.note})' if post.note else ''))
        log(f'  {post.scopes} TK scope(s), {len(post.quotes)} partial quote(s), {len(post.sources)} source(s)')
        if self.dry_run or self.api is None:
            log(f'----- series post markdown ({stype}) -----')
            log(post.markdown)
            log('-------------------------------------------')
            return self.result(post, C.fake_id(f'series:{stype}:{self.today}'), published=False)
        items = self.recent_series_items()
        existing = self.todays_item(stype, items)
        self.resume(items, exclude=existing, reserve=post.scopes + reserve)
        if existing and existing.get('status') == 'public':
            log(f"  today's post already published: {existing['id']}")
            self.file(stype, existing['id'])
            return self.result(post, existing['id'], published=True)
        if self.spent + post.scopes > self.budget:
            log(f'  ! not enough blyg AI budget left this run ({self.spent} of {self.budget} spent); '
                'no series post today')
            return None
        if existing:
            item_id, content = existing['id'], existing['contentMd']
            log(f"  resuming today's draft {item_id}")
        else:
            item = self.api.create_thread(post.markdown)
            item_id, content = item['id'], post.markdown
            log(f'  created draft {item_id}')
        if not self.finish(item_id, content, stype):
            self.result(post, item_id, published=False)   # recorded so the subject is not reused
            return None
        return self.result(post, item_id, published=True)

    def result(self, post, item_id, published):
        r = {'type': post.type, 'id': item_id, 'title': post.title, 'teaser': post.teaser, 'subject': post.subject,
             'subject_title': post.subject_title, 'sources': post.sources, 'author': post.author,
             'published': published, 'markdown': post.markdown}
        self.report['series'] = r
        return r

    def resume(self, items, exclude=None, reserve=0):
        """Finish drafts earlier runs left, oldest first, while the budget allows."""
        drafts = [it for it in items if it.get('status') == 'draft' and it is not exclude
                  and (not exclude or it.get('id') != exclude.get('id'))]
        drafts.sort(key=lambda it: it.get('created') or it.get('updated') or '')
        for it in drafts:
            stype = series_type_of(it['contentMd'])
            need = len(pending_scopes(it['contentMd']))
            if self.spent + need + reserve > self.budget:
                log(f"  leaving unfinished {stype} draft {it['id']} for a later run (needs {need} AI call(s))")
                continue
            log(f"Resuming unfinished {stype} draft {it['id']} from {series_line_date(it['contentMd'])}")
            if self.finish(it['id'], it['contentMd'], stype):
                self.mark_published(it['id'])

    def mark_published(self, item_id):
        for entry in (self.history.get('days') or {}).values():
            s = (entry or {}).get('series')
            if s and s.get('id') == item_id:
                s['published'] = True

    def finish(self, item_id, content, stype):
        """Generate the missing scopes, publish (dropping a refused quote or link once), file. True when published."""
        try:
            content = self.generate(item_id, content)
        except GenerationFailed as e:
            log(f'  ! {e}')
            return False
        if not self.publish(item_id, content, stype):
            return False
        self.file(stype, item_id)
        return True

    def generate(self, item_id, content):
        dropped = set()
        while True:
            todo = pending_scopes(content)
            if not todo:
                return content
            if self.spent >= self.budget:
                raise GenerationFailed(f'the run\'s AI budget ({self.budget}) is spent; draft {item_id} waits')
            idx = todo[0]
            self.report['blyg_generate_calls'] += 1
            try:
                result = self.api.generate(item_id, idx)
            except BlygError as e:
                if isinstance(e, AuthError):
                    raise
                bad = e.details.get('id')
                if e.status == 400 and 'unresolvable source' in e.message and bad and bad not in dropped:
                    log(f'    source {bad} no longer resolves; dropping it')
                    dropped.add(bad)
                    content = self.drop_source(content, bad)
                    self.api.patch_item(item_id, content)
                    continue
                raise GenerationFailed(f'generation failed (HTTP {e.status}: {e.message}); draft {item_id} stays '
                                       'and the next choosing run resumes it') from e
            content = result['contentMd']
            log(f"    generated scope {idx}: {len(result.get('text') or '')} chars with {result.get('model')}")

    @staticmethod
    def drop_source(content, source_id):
        from blyg_sync import drop_source
        return drop_source(content, source_id)

    def publish(self, item_id, content, stype):
        note = f'{TYPES[stype][0]}, {self.today.isoformat()}'
        for attempt in (0, 1):
            try:
                resp = self.api.publish(item_id, note=note)
                break
            except BlygError as e:
                if isinstance(e, AuthError) or attempt:
                    if not isinstance(e, AuthError):
                        log(f'  ! publish refused again ({e}); draft {item_id} stays')
                        return False
                    raise
                errors = e.details.get('errors') if e.status == 400 else None
                if not isinstance(errors, list):
                    log(f'  ! publish refused ({e}); draft {item_id} stays')
                    return False
                quotes = {m.group(1) for x in errors if isinstance(x, dict)
                          for m in [QUOTE_DIRECTIVE.match(str(x.get('directive', '')))] if m}
                links = F.unresolved_link_ids(e)
                if not quotes and not links:
                    log(f'  ! publish refused ({e}); draft {item_id} stays')
                    return False
                for q in sorted(quotes):
                    log(f'  ! a quote from {q} was refused; dropping it')
                    content = drop_quote(content, q)
                if links:
                    log(f'  ! {len(links)} link(s) no longer resolve; writing them as plain text')
                    content = F.unlink(content, links)
                self.api.patch_item(item_id, content)
        if resp.get('unresolvedHandles'):
            log(f"  note: Studio found no contact for {', '.join(resp['unresolvedHandles'])}")
        log(f"  published {stype} version {resp.get('version')}: {self.site}t/{item_id}/")
        return True

    # -- hoppers
    def hopper(self, stype):
        if self._hoppers is None:
            self._hoppers = {h.get('slug'): h for h in self.api.hoppers()}
        h = self._hoppers.get(stype)
        if h:
            return h
        name = TYPES[stype][2]
        log(f'  creating public hopper "{name}" at /h/{stype}/')
        h = self.api.create_hopper(stype)    # the slug comes from the name and freezes when it goes public
        if h.get('slug') != stype:
            log(f"  ! the server gave slug {h.get('slug')!r}, not {stype!r}; using it")
        h = self.api.patch_hopper(h['id'], public=True)
        if name != stype:
            h = self.api.patch_hopper(h['id'], name=name)
        self._hoppers[stype] = h
        return h

    def file(self, stype, item_id):
        try:
            h = self.hopper(stype)
            self.api.file(h['id'], F.OWN_SUBSCRIPTION, item_id)
            log(f'  filed into /h/{h.get("slug") or stype}/')
        except BlygError as e:
            if isinstance(e, AuthError) and e.status == 401:
                raise
            log(f'  ! could not file into the {stype} hopper ({e}); the token needs owner:manage. '
                'The post is published; file it by hand or rerun with a token that can.')
