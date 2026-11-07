#!/usr/bin/env python3
"""
Keep a Wikipedia-Main-Page-style front page on the World Machines blyg.

The page is one published thread. Studio's static-front-page setting
(`frontPage` = its id) shows it at the blyg's root and moves the latest-items
list to /posts/. The operator sets that once; this script never touches it.

Sections:
  1. Welcome: what World Machines is, live counts, the main links.
  2. Today's featured note (Mondays, and any day the series post fails): an
     author-first pick with a 120-180-word blurb disclosed as generated. On
     Tuesday to Sunday the block is "Today's series" instead: the day's series
     post (scripts/blyg_series.py), its title, a short teaser written here
     without any AI call, and a link. See "The weekly rhythm" below.
  3. Did you know: 4-6 one-line hooks from other shortlisted notes. Each hook
     is an `impyrt` scope (generated elsewhere, disclosed as generated); the
     link to its note sits outside the scope, because Studio strips bracket
     syntax from generated text.
  4. From the members: the latest digest and the newest posts filed into the
     members hopper (/h/members/).
  5. Explore: most-linked notes, the glossary, books read, members' notes.

How the featured note is chosen:
  * Eligible: published notes with real prose (length limits), no
    index/README/stub/multi-part notes, nothing featured or used as a "did you
    know" in the last 90 days (tools/blyg-front/history.json). Each is scored
    by area (synthesis, glossary, member notes > reading notes > entities) and
    inbound wikilinks.
  * Authors first, then posts. Every note belongs to one author: its member,
    or "commons" for the shared notes no one is named on (reading notes,
    summaries, synthesis, glossary, entities). A randomizer seeded by the date
    picks an author uniformly from those with an eligible note, skipping
    yesterday's featured author when anyone else is left, then one of that
    author's notes weighted by score. One prolific author therefore gets one
    author's share of the days, not a share proportional to how much they wrote.
  * Hook candidates (~30) are dealt round-robin across authors in a shuffled
    order, then spread across books and areas. On the page, a member gets at
    most one hook and commons at most two. The featured author's notes are
    used only when nothing else fills the minimum.
  * One Workers AI call (REST, Gemma 4) writes the hooks from those candidates.
    Its JSON is validated; anything unusable falls back to the deterministic
    order, so the page still updates. The model never picks the featured
    note.
  * The blurb is a blyg TK scope whose source is the featured note (one call
    on the blyg's shared AI budget), so the published version records which
    note and model produced it. If the blyg refuses (budget spent, provider
    error), a second Workers AI REST call writes the blurb and it goes in as
    `impyrt`; if that fails too, the note's own summary is quoted, undisclosed
    because nothing generated it here.

The weekly rhythm (blyg_series.py), by the UTC weekday of the choosing run:
  Mon featured note · Tue open questions · Wed concept dossier · Thu book
  companion · Fri side by side · Sat term watch · Sun oracle cast.
  Each series post is its own thread with partial quotes of the notes and one
  or two TK scopes, published once and filed into a public hopper per series
  (/h/questions/, /h/concepts/, /h/books/, /h/side-by-side/, /h/terms/,
  /h/oracle/). Only the choosing run builds one. On a series day the page
  makes no blurb call of its own, so the token spends at most 2 blyg TK calls
  for the series (RUN_TK_BUDGET caps a run at 5, of the token's 10 a day). If
  the post cannot be published (no subject, budget spent, provider error) the
  page shows the featured note, and the draft is finished by the next choosing
  run. The "Did you know" hooks stay daily. History day entries gain
  "series": {type, id, title, subject, sources, author, published}; each
  series excludes its own subjects for 90 days.

The featured block changes at most once a UTC day (the history file is the
guard: a day entry with `chosen_by`). A run that is not choosing (the evening run, or a re-run on the same
day) keeps the featured and did-you-know block exactly as it is in the working
copy and refreshes the other sections. The thread is republished only when its
text changed. Every publish is one feed.xml entry; Studio has no way to keep a
republish out of the feed.

Usage (from website/):
  python scripts/blyg_front.py --dry-run          # print the markdown and picks; no blyg writes
  python scripts/blyg_front.py --create           # first run: create + publish, print the id
  python scripts/blyg_front.py                    # daily: update thread BLYG_FRONT_ID
  python scripts/blyg_front.py --members-only     # refresh members/explore; never chooses
  python scripts/blyg_front.py --dry-run --no-ai --series-only concepts --date 2026-11-11
                                                  # print one series post; offline without a token
  python scripts/blyg_front.py --series-only books   # build, publish and file one series post now
  python scripts/blyg_front.py --no-series        # the featured note whatever the weekday

Environment:
  BLYG_FRONT_TOKEN  Studio REST token (owner:read owner:draft owner:publish, and
                    owner:manage to create the series hoppers and file posts into
                    them; without it posts are published but not filed); a
                    separate token is its own grant, so its AI calls do not
                    count against the digest token's per-grant AI limit.
  BLYG_TOKEN        used when BLYG_FRONT_TOKEN is not set
  BLYG_API_BASE     default https://blyg.worldmachines.org/api ({mount}/api; Studio 0.51,
                    private API contract 5.2.0, through blyg_sync.BlygApi)
  BLYG_SITE         public base; default BLYG_API_BASE minus /api
  BLYG_FRONT_ID     the front-page thread's id (or --id)
  BLYG_HOPPER_SLUG  default members
  BLYG_FRONT_BLURB  tk (default) or impyrt
  CF_AI_TOKEN, CLOUDFLARE_ACCOUNT_ID   Workers AI REST
  WORKERS_AI_BASE   default https://api.cloudflare.com/client/v4 (tests point it elsewhere)

Stdlib only.
"""
import argparse
import json
import math
import os
import random
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
IMPORT_DIR = REPO / 'tools' / 'blyg-import'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(IMPORT_DIR))

import corpus as C  # noqa: E402  (tools/blyg-import: parsing, link resolution)
from blyg_sync import (  # noqa: E402  (same request layer as the twice-daily sync)
    DIGEST_PREFIX, AuthError, BlygApi, BlygError, clean_label, norm_base, site_from_api_base,
    urllib_transport,
)

DEFAULT_API_BASE = 'https://blyg.worldmachines.org/api'
DEFAULT_SLUG = 'members'
AI_BASE = 'https://api.cloudflare.com/client/v4'
MODEL = '@cf/google/gemma-4-26b-a4b-it'
STATE_PATH = IMPORT_DIR / 'state.json'
AUTHORS_PATH = IMPORT_DIR / 'authors.json'
CONFIG_PATH = IMPORT_DIR / 'config.json'
HISTORY_PATH = REPO / 'tools' / 'blyg-front' / 'history.json'

FRONT_TITLE = 'World Machines'
FEATURED_HEADING = "## Today's featured note"
SERIES_HEADING = "## Today's series: "   # replaces the featured note on series days (blyg_series)
BLOCK_START = re.compile(r"^## Today's (?:featured note|series: )", re.M)
DYK_HEADING = '## Did you know…'
DYK_FALLBACK_HEADING = '## From the notes'
MEMBERS_HEADING = '## From the members'
EXPLORE_HEADING = '## Explore'

EXCLUDE_DAYS = 90       # a note featured or used as a hook stays out this long
HISTORY_KEEP_DAYS = 400
SHORTLIST_SIZE = 30
PER_GROUP = 2           # at most this many shortlisted notes per book / member / commons area
COMMONS = 'commons'     # the author key of the shared notes no member is named on
HOOKS_PER_AUTHOR = {COMMONS: 2}   # hooks per author on one page; members get 1
MAX_READING = 14        # reading notes in a shortlist (they are half the corpus)
DYK_MIN, DYK_MAX = 4, 6
LEN_MIN, LEN_MAX = 1200, 16000   # plain-text characters
EXCERPT_CHARS = 500
BLURB_SOURCE_CHARS = 9000
MEMBER_POSTS = 5
TOP_LINKED = 10
OWN_SUBSCRIPTION = '~own'   # Studio's subscription id for our own items in a hopper
DIGEST_SCAN_PAGES = 5  # /items is ordered by `updated`; a digest is near the top

AREA_WEIGHT = {
    'synthesis': 3.0, 'glossary': 3.0, 'member': 2.5, 'summaries': 2.0,
    'contributions': 2.0, 'reading': 1.5, 'entities': 1.0,
}
ARTICLE_DIR = re.compile(r'-\d{8}-[0-9a-f]{6}$')   # a submitted link, not a book
PART_TITLE = re.compile(r'\(part (\d+) of (\d+)\)\s*$', re.I)

WM_SITE = 'https://worldmachines.org/'
WM_HOPPERS = 'https://worldmachines.org/hoppers'


def log(msg=''):
    print(msg, flush=True)


# ---------------------------------------------------------------- text helpers

def label(text, limit=90):
    """A link label: one line, no brackets at all (Studio's link and TK grammar)."""
    return clean_label(text, limit)


def link(item_id, text):
    return f'[[{item_id} | {label(text)}]]'


def plain(md):
    """Markdown body → plain prose, for lengths, excerpts and model input."""
    text = C.WIKILINK_RE.sub(lambda m: C.parse_link(m.group(2)).display, md)
    text = re.sub(r'^```.*?^```', ' ', text, flags=re.S | re.M)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^\s{0,3}(#{1,6}|>|[-*+]|\d+[.)])\s+', '', text, flags=re.M)
    text = re.sub(r'[*_`|]+', '', text)
    text = re.sub(r'^-{3,}\s*$', ' ', text, flags=re.M)
    return re.sub(r'\s+', ' ', text).strip()


def clip(text, n):
    text = re.sub(r'\s+', ' ', text or '').strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(' ', 1)[0]
    return cut.rstrip(',;:') + '…'


def safe_generated(text, limit=None):
    """Text going into an impyrt scope: no Studio grammar, one paragraph."""
    text = re.sub(r'\[/?TK\]|\[=\]', '', text or '')
    text = re.sub(r'[\[\]]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return clip(text, limit) if limit else text


def words(text):
    return len(re.findall(r"\S+", text or ''))


# ---------------------------------------------------------------- the corpus

class Corpus:
    """The notes, as the importer published them: titles, authors, link graph, blyg ids."""

    def __init__(self, root=REPO, state_path=STATE_PATH, authors_path=AUTHORS_PATH, config_path=CONFIG_PATH,
                 notes=None, state=None, authors=None):
        cfg = json.loads(Path(config_path).read_text()) if config_path and Path(config_path).exists() else {}
        self.notes = notes if notes is not None else C.load_corpus(
            Path(root), cfg.get('include', ['raw-notes/**/*.md', 'wiki/**/*.md']), cfg.get('exclude', []))
        self.by_path = {n.path: n for n in self.notes}
        self.state = state if state is not None else json.loads(Path(state_path).read_text()).get('items', {})
        self.authors = authors or C.Authors.load(Path(authors_path))
        self.index = C.LinkIndex(self.notes)
        self.outbound = {}   # path → paths of the other notes it links to
        self.inbound = self._inbound()
        self._plain = {}

    def _inbound(self):
        """path → number of distinct other notes that link to it (and fills `outbound`)."""
        sources = {}
        for n in self.notes:
            targets = set()

            def collect(segment, n=n, targets=targets):
                for m in C.WIKILINK_RE.finditer(segment):
                    tgt = C.parse_link(m.group(2)).target
                    if tgt:
                        res = self.index.resolve(tgt, n)
                        if res.note is not None and res.note is not n:
                            targets.add(res.note.path)
                return segment
            C.map_outside_code(n.body, collect)
            for key, _ in C.FOOTER_KEYS:
                for raw in C.as_list(n.front.get(key)):
                    inner = raw[2:-2] if raw.startswith('[[') and raw.endswith(']]') else raw
                    res = self.index.resolve(C.parse_link(inner).target, n)
                    if res.note is not None and res.note is not n:
                        targets.add(res.note.path)
            self.outbound[n.path] = targets
            for t in targets:
                sources[t] = sources.get(t, 0) + 1
        return sources

    # -- per note
    def item_id(self, path):
        e = self.state.get(path)
        return e['id'] if e and e.get('published_version') else None

    def plain(self, note):
        if note.path not in self._plain:
            self._plain[note.path] = plain(note.body)
        return self._plain[note.path]

    def area(self, note):
        p = note.path.split('/')
        if p[0] == 'wiki':
            return 'wiki'
        if p[0] != 'raw-notes' or len(p) < 3:
            return 'top'
        if p[1] == 'commons':
            return p[2] if len(p) > 3 else 'commons'
        return 'member'

    def group(self, note):
        """The diversity bucket: one book, one member, or one commons area."""
        p = note.path.split('/')
        area = self.area(note)
        if area == 'reading':
            return 'book:' + p[3]
        key = self.author_key(note)
        if key != COMMONS:
            return key  # a member's own notes and their contributions are one bucket
        if area == 'contributions':
            return 'contribution:' + (p[3] if len(p) > 3 else p[-1])
        return 'commons:' + area

    def author_key(self, note):
        """Who a note counts as for fairness: 'member:<name>', or COMMONS for shared notes."""
        if self.area(note) == 'member' or self.area(note) == 'contributions':
            who = self.authors.author_for(note)
            if who and who.get('name'):
                return 'member:' + who['name']
            if self.area(note) == 'member':
                return 'member:' + note.path.split('/')[1]
        return COMMONS

    def author(self, note):
        who = self.authors.author_for(note)
        return (who or {}).get('name') or ''

    def book_slug(self, note):
        p = note.path.split('/')
        return p[3] if self.area(note) == 'reading' and len(p) > 4 else None

    def context(self, note):
        """'by X' / 'from <book>' / area, for display and for the model."""
        bits = []
        who = self.author(note)
        if who:
            bits.append(f'by {who}')
        slug = self.book_slug(note)
        if slug:
            bits.append(f'reading notes on {self.book_title(slug)}')
        elif not who:
            bits.append({'synthesis': 'synthesis note', 'glossary': 'glossary entry', 'summaries': 'book summary',
                         'entities': 'entity note'}.get(self.area(note), 'shared note'))
        return ', '.join(bits)

    def excerpt(self, note, n=EXCERPT_CHARS):
        summary = note.front.get('summary') if isinstance(note.front.get('summary'), str) else ''
        text = (summary.strip() + ' ' if summary else '') + self.plain(note)
        return clip(text, n)

    # -- books
    def books(self):
        """[(slug, title, path to link)] for every book read: its summary note, else its first chapter note."""
        out = []
        reading = sorted({self.book_slug(n) for n in self.notes if self.book_slug(n)})
        for slug in reading:
            if ARTICLE_DIR.search(slug):
                continue
            summary = self.book_summary(slug)
            if summary and self.item_id(summary.path):
                path = summary.path
            else:
                chapters = sorted(n.path for n in self.notes if self.book_slug(n) == slug and self.item_id(n.path))
                if not chapters:
                    continue
                path = chapters[0]
            out.append((slug, self.book_title(slug), path))
        return out

    def book_summary(self, slug):
        """The book's summary note: summaries/<slug>.md, else the summary whose sources cite the book most."""
        if not hasattr(self, '_summaries'):
            self._summaries = {}
            stems = {}
            for n in self.notes:
                s = self.book_slug(n)
                if s:
                    stems.setdefault(s, set()).add(n.stem.lower())
            summaries = [n for n in self.notes if n.path.startswith('raw-notes/commons/summaries/')]
            for s, mine in stems.items():
                exact = self.by_path.get(f'raw-notes/commons/summaries/{s}.md')
                if exact:
                    self._summaries[s] = exact
                    continue
                best = max(summaries, default=None,
                           key=lambda n: len(mine & {C.link_key(x) for x in C.as_list(n.front.get('sources'))}))
                if best and len(mine & {C.link_key(x) for x in C.as_list(best.front.get('sources'))}) >= 3:
                    self._summaries[s] = best
        return self._summaries.get(slug)

    def book_title(self, slug):
        n = self.book_summary(slug)
        title = n.title if n else C.humanize(slug)
        title = re.sub(r'[*_]', '', title)
        title = re.split(r' — | \(', title, maxsplit=1)[0].strip() or title
        if len(title) > 50 and ':' in title:
            title = title.split(':', 1)[0].strip()
        return title

    # -- eligibility and scoring
    def eligible(self, note):
        """None when the note can be featured, else why not."""
        if not self.item_id(note.path):
            return 'not published'
        if f'{note.path}#part-2' in self.state:
            return 'split into parts'
        stem = note.stem.lower()
        if stem in ('index', 'readme') or stem.startswith('_'):
            return 'index'
        area = self.area(note)
        if area in ('wiki', 'top', 'commons'):
            return 'project page'
        m = PART_TITLE.search(note.title)
        if m and m.group(2) != '1':
            return 'one part of a longer essay'
        if str(note.front.get('status', '')).lower() in ('stub', 'draft', 'todo'):
            return 'stub'
        size = len(self.plain(note))
        if size < LEN_MIN:
            return 'too short'
        if size > LEN_MAX:
            return 'too long'
        return None

    def score(self, note):
        return AREA_WEIGHT.get(self.area(note), 1.0) * (1 + math.log1p(self.inbound.get(note.path, 0)))

    def most_linked(self, n=TOP_LINKED):
        rows = [(c, p) for p, c in self.inbound.items()
                if self.item_id(p) and self.by_path[p].stem.lower() not in ('index', 'readme')
                and self.area(self.by_path[p]) not in ('wiki', 'top')]
        rows.sort(key=lambda r: (-r[0], r[1]))
        return [(self.by_path[p], c) for c, p in rows[:n]]


def eligible_pool(corpus, recent_paths):
    return [n for n in corpus.notes if n.path not in recent_paths and corpus.eligible(n) is None]


def by_author(corpus, notes, rng=None):
    """{author key: notes}, each list best first; with `rng`, a score-weighted random order instead."""
    out = {}
    for n in notes:
        out.setdefault(corpus.author_key(n), []).append(n)
    for key, mine in out.items():
        if rng is None:
            mine.sort(key=lambda n: (-corpus.score(n), n.path))
        else:
            # Efraimidis–Spirakis: sorting by u ** (1 / weight) is a weighted shuffle.
            mine.sort(key=lambda n: (n.path,))
            keyed = [(rng.random() ** (1.0 / max(corpus.score(n), 1e-6)), n) for n in mine]
            keyed.sort(key=lambda kv: -kv[0])
            mine[:] = [n for _, n in keyed]
    return out


def day_rng(today):
    """The same picks for every run on one UTC day, different picks across days."""
    return random.Random(f'wm-front:{today.isoformat()}')


def pick_featured(corpus, recent_paths, rng, avoid_author=None):
    """Authors first: choose an author uniformly, then one of their notes weighted by score."""
    queues = by_author(corpus, eligible_pool(corpus, recent_paths), rng)
    if not queues:
        return None
    authors = sorted(queues)
    if avoid_author in authors and len(authors) > 1:
        authors.remove(avoid_author)
    author = rng.choice(authors)
    return queues[author][0]


def shortlist(corpus, recent_paths, size=SHORTLIST_SIZE, per_group=PER_GROUP, max_reading=MAX_READING,
              rng=None, exclude=()):
    """Hook candidates, dealt round-robin across authors, then capped per book / area.

    Without `rng` the order is deterministic: authors by their best note, each author's notes best first.
    """
    skip = set(recent_paths) | {n.path for n in exclude}
    queues = by_author(corpus, eligible_pool(corpus, skip), rng)
    authors = sorted(queues, key=lambda a: (-corpus.score(queues[a][0]), a))
    if rng is not None:
        authors = sorted(queues)
        rng.shuffle(authors)
    picked, per, reading = [], {}, 0
    pos = {a: 0 for a in authors}
    while len(picked) < size and authors:
        for a in list(authors):
            if len(picked) >= size:
                break
            q = queues[a]
            while pos[a] < len(q):
                n = q[pos[a]]
                pos[a] += 1
                g = corpus.group(n)
                if per.get(g, 0) >= per_group:
                    continue
                if corpus.area(n) == 'reading' and reading >= max_reading:
                    continue
                picked.append(n)
                per[g] = per.get(g, 0) + 1
                reading += corpus.area(n) == 'reading'
                break
            if pos[a] >= len(q):
                authors.remove(a)
    return picked


def spread_hooks(corpus, entries, featured, limit=None):
    """Keep at most HOOKS_PER_AUTHOR hooks per author (members 1), the featured author last.

    `entries` is [(note, hook)] in preference order. Notes over the cap are used only when the page would
    otherwise have fewer than DYK_MIN hooks.
    """
    limit = limit or DYK_MAX
    fa = corpus.author_key(featured)
    count = {fa: 1}
    kept, spare = [], []
    for n, hook in entries:
        a = corpus.author_key(n)
        if count.get(a, 0) < HOOKS_PER_AUTHOR.get(a, 1) and len(kept) < limit:
            kept.append((n, hook))
            count[a] = count.get(a, 0) + 1
        else:
            spare.append((n, hook))
    for e in spare:
        if len(kept) >= DYK_MIN:
            break
        kept.append(e)
    return kept


# ---------------------------------------------------------------- history

def load_history(path=HISTORY_PATH):
    path = Path(path)
    if not path.exists():
        return {'version': 1, 'days': {}}
    data = json.loads(path.read_text())
    data.setdefault('days', {})
    return data


def recent_paths(history, today, days=EXCLUDE_DAYS):
    """Every note featured or used as a hook within `days` before `today` (inclusive)."""
    cutoff = today - timedelta(days=days)
    out = set()
    for day, entry in history.get('days', {}).items():
        try:
            d = date.fromisoformat(day)
        except ValueError:
            continue
        if cutoff <= d <= today:
            if entry.get('featured', {}).get('path'):
                out.add(entry['featured']['path'])
            out.update(x['path'] for x in entry.get('dyk', []) if x.get('path'))
    return out


def save_history(history, path=HISTORY_PATH, today=None):
    if today:
        cutoff = today - timedelta(days=HISTORY_KEEP_DAYS)
        history['days'] = {d: e for d, e in history['days'].items() if d >= cutoff.isoformat()}
    history['days'] = dict(sorted(history['days'].items()))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(history, indent=1, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


# ---------------------------------------------------------------- Workers AI

class AiError(Exception):
    pass


class WorkersAI:
    """Workers AI over REST (billed to the Cloudflare account, not the blyg's budget)."""

    def __init__(self, account_id, token, model=MODEL, base=AI_BASE, transport=urllib_transport):
        self.account_id, self.token, self.model = account_id, token, model
        self.base = base.rstrip('/')
        self.transport = transport
        self.calls = 0

    def chat(self, system, user, max_tokens=1500, temperature=0.4):
        url = f'{self.base}/accounts/{self.account_id}/ai/run/{self.model}'
        body = json.dumps({
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'max_tokens': max_tokens, 'temperature': temperature,
            'chat_template_kwargs': {'enable_thinking': False},
        }).encode()
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        self.calls += 1
        try:
            status, _, raw = self.transport('POST', url, headers, body)
        except Exception as e:  # network
            raise AiError(f'Workers AI request failed: {e}') from e
        if status != 200:
            raise AiError(f'Workers AI → HTTP {status}: {raw[:300].decode(errors="replace")}')
        try:
            payload = json.loads(raw)
        except ValueError as e:
            raise AiError('Workers AI returned invalid JSON') from e
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise AiError(f'Workers AI returned no result: {str(payload)[:300]}')
        text = None
        choices = result.get('choices')
        if isinstance(choices, list) and choices:
            text = (choices[0].get('message') or {}).get('content')
        if text is None:
            text = result.get('response')
        if isinstance(text, (dict, list)):
            text = json.dumps(text)
        if not isinstance(text, str) or not text.strip():
            raise AiError('Workers AI returned no text')
        return text


SELECT_SYSTEM = (
    'You are the editor of the front page of World Machines, a group that reads history and theory together to '
    'build psychohistorical models from Venkatesh Rao\'s idea of "world machines": large systems such as the '
    'modernity machine that organize civilizations, and how they rise, compete and break down. '
    'You answer with JSON only.'
)


def selection_prompt(featured, cands, corpus):
    lines = [
        'Write the "Did you know" hooks for the front page from the candidates below. '
        f'Today\'s featured note is already chosen ({featured.title}, {corpus.context(featured)}); '
        'do not write a hook for it.',
        '',
        'Rubric, in order: relevance to World Machines themes (psychohistory, world machines, modernity, '
        'civilizational dynamics, how big systems shape people); surprise (a reader learns something unexpected); '
        'self-containedness (it makes sense without its neighbours); variety (different books, members and topics).',
        '',
        'Answer with one JSON object and nothing else:',
        '{"did_you_know": [{"key": "<key>", "hook": "that <fact>"}, ...]}',
        '',
        f'- "did_you_know": {DYK_MIN} to {DYK_MAX} entries, each a different note, from as many different '
        'authors as you can (one note per member at most).',
        '- Each hook starts with "that", states one surprising, specific fact taken from that candidate\'s excerpt '
        '(never invent one), has at most 25 words, and has no question mark, brackets, links or markdown.',
        '',
        'Candidates:',
    ]
    for i, n in enumerate(cands, 1):
        lines += ['', f'[C{i:02d}] {n.title} ({corpus.context(n)}; linked from {corpus.inbound.get(n.path, 0)} notes)',
                  corpus.excerpt(n)]
    return '\n'.join(lines)


def parse_json_object(text):
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        raise ValueError('no JSON object in the answer')
    return json.loads(text[start:end + 1])


def clean_hook(hook):
    """Normalize a hook to 'that …' with no grammar, or None when unusable."""
    if not isinstance(hook, str):
        return None
    h = safe_generated(hook)
    h = re.sub(r'^(?:\.\.\.|…)\s*', '', h)
    h = re.sub(r'^did you know\s*', '', h, flags=re.I)
    h = re.sub(r'^(?:\.\.\.|…)\s*', '', h)
    h = h.rstrip(' ?.!')
    if not re.match(r'^that\s+\S', h, re.I):
        return None
    h = 'that' + h[4:]
    if words(h) < 5 or words(h) > 40:
        return None
    return h


def validate_selection(data, cands, featured, corpus):
    """{'featured': Note, 'dyk': [(Note, hook)], 'why': str} from the model's JSON, or raise ValueError.

    The featured note is chosen before the model is asked (authors first); the model writes hooks only.
    """
    if not isinstance(data, dict):
        raise ValueError('answer is not an object')
    keys = {f'C{i:02d}': n for i, n in enumerate(cands, 1)}

    def note_for(key):
        if not isinstance(key, str):
            return None
        k = key.strip().strip('[]').upper()
        m = re.match(r'^C?(\d{1,2})$', k)
        return keys.get(f'C{int(m.group(1)):02d}') if m else None

    entries, seen = [], {featured.path}
    for entry in data.get('did_you_know') or []:
        if not isinstance(entry, dict):
            continue
        n = note_for(entry.get('key') or entry.get('id'))
        hook = clean_hook(entry.get('hook'))
        if n is None or hook is None or n.path in seen:
            continue
        seen.add(n.path)
        entries.append((n, hook))
    dyk = spread_hooks(corpus, entries, featured)
    if len(dyk) < DYK_MIN:
        raise ValueError(f'only {len(dyk)} usable did-you-know hooks')
    return {'featured': featured, 'dyk': dyk, 'why': ''}


def fallback_selection(cands, corpus, featured):
    """The deterministic hooks: candidates in their round-robin order, one group each where possible."""
    rest, groups = [], {corpus.group(featured)}
    for n in cands:
        if n.path != featured.path and corpus.group(n) not in groups:
            rest.append((n, None))
            groups.add(corpus.group(n))
    rest += [(n, None) for n in cands if n.path != featured.path and (n, None) not in rest]
    return {'featured': featured, 'dyk': spread_hooks(corpus, rest, featured), 'why': ''}


BLURB_SYSTEM = (
    'You write short, accurate introductions to notes for the World Machines front page. '
    'Plain prose only: no headings, lists, links, markdown or quotations longer than a phrase.'
)


def blurb_instruction():
    """The TK instruction (and the REST prompt) for the featured blurb."""
    return (
        'Write a 120 to 180 word blurb that introduces this note to a newcomer to World Machines, a group building '
        "psychohistorical models from Venkatesh Rao's theory of world machines. Say what the note argues or shows, "
        'and why it matters for understanding how civilizations and their big systems change. '
        'One paragraph of plain prose: no headings, lists, links, or quotations longer than a short phrase. '
        "Use only what the note says, and don't invent claims."
    )


def blurb_prompt(note, corpus):
    return (f'{blurb_instruction()}\n\nThe note: "{note.title}" ({corpus.context(note)}).\n\n'
            f'{clip(corpus.plain(note), BLURB_SOURCE_CHARS)}')


def clean_blurb(text):
    t = safe_generated(re.sub(r'^\s*#+.*$', '', text or '', flags=re.M))
    t = re.sub(r'^(?:here is|here\'s)[^:]*:\s*', '', t, flags=re.I)
    if not 60 <= words(t) <= 260:
        return None
    return t


# ---------------------------------------------------------------- page sections

def welcome_section(corpus, site, posts_path, hopper_slug):
    members = len(corpus.authors.authors)
    books = len(corpus.books())
    notes = sum(1 for k, e in corpus.state.items() if e.get('published_version') and '#part-' not in k)
    return '\n'.join([
        f'# {FRONT_TITLE}',
        '',
        'World Machines is a group of readers and writers building psychohistorical models from Venkatesh Rao\'s '
        'theory of world machines: the large systems, like the modernity machine, that organize how civilizations '
        f'grow, compete and come apart. This blyg holds the group\'s shared notes: **{notes:,} notes** from '
        f'**{members} members**, across **{books} books read** so far.',
        '',
        f'[worldmachines.org]({WM_SITE}) · [All posts]({site}{posts_path}/) · '
        f'[Members\' hopper]({site}h/{hopper_slug}/) · [Propose a hopper]({WM_HOPPERS})',
    ])


def featured_section(note, corpus, blurb_md):
    item_id = corpus.item_id(note.path)
    ctx = corpus.context(note)
    lines = [
        FEATURED_HEADING,
        '',
        f'**{link(item_id, note.title)}**' + (f' · *{label(ctx, 120)}*' if ctx else ''),
        '',
        blurb_md,
        '',
        f'{link(item_id, "Read the full note →")}',
    ]
    return '\n'.join(lines)


def tk_blurb(note, corpus):
    return f'[TK]{blurb_instruction()} ![[{corpus.item_id(note.path)}]][/TK]'


def impyrt(text, model=MODEL):
    return f'[TK]impyrt {model}={safe_generated(text)}[/TK]'


def excerpt_blurb(note, corpus):
    """Fallback when nothing could be generated: the note's own words, quoted, not disclosed as generated."""
    return '> ' + safe_generated(corpus.excerpt(note, 700)) +'\n\n*From the note itself; no summary could be generated today.*'


def dyk_section(dyk, corpus, model=MODEL):
    """`dyk` is [(note, hook or None)]. With hooks: 'Did you know…'; without: summary lines from the notes."""
    if dyk and all(h for _, h in dyk):
        lines = [DYK_HEADING, '']
        for n, hook in dyk:
            lines.append(f'- …{impyrt(hook, model)}? ({link(corpus.item_id(n.path), n.title)})')
        return '\n'.join(lines)
    lines = [DYK_FALLBACK_HEADING, '']
    for n, _ in dyk:
        summary = n.front.get('summary') if isinstance(n.front.get('summary'), str) else ''
        text = clip(summary or corpus.plain(n), 220)
        lines.append(f'- **{link(corpus.item_id(n.path), n.title)}**: {safe_generated(text)}')
    return '\n'.join(lines)


def members_section(digest, posts, site, hopper_slug):
    hopper_url = f'{site}h/{hopper_slug}/'
    lines = [MEMBERS_HEADING, '']
    if digest:
        lines += [f'Latest digest: {link(digest["id"], digest["title"])}', '']
    if posts:
        for p in posts:
            by = f' — {label(p["author"], 60)}' if p.get('author') else ''
            lines.append(f'- [{label(p["title"])}]({p["url"]}){by}')
        lines += ['', f'[Everything in the members\' hopper →]({hopper_url})']
    else:
        lines.append(
            'Nothing from member blygs yet. Members who keep a blyg can '
            f'[propose a hopper]({WM_HOPPERS}) of their World Machines posts; filed posts appear here and in '
            f'[the members\' hopper]({hopper_url}).')
    return '\n'.join(lines)


def explore_section(corpus, site, posts_path):
    lines = [EXPLORE_HEADING, '']
    top = corpus.most_linked()
    if top:
        lines += ['**Most-linked notes:** ' + ' · '.join(link(corpus.item_id(n.path), n.title) for n, _ in top), '']
    gloss_readme = 'raw-notes/commons/glossary/README.md'
    terms = sorted((n for n in corpus.notes if n.path.startswith('raw-notes/commons/glossary/')
                    and n.path != gloss_readme and corpus.item_id(n.path)), key=lambda n: n.title.lower())
    if corpus.item_id(gloss_readme) or terms:
        head = link(corpus.item_id(gloss_readme), 'The glossary') if corpus.item_id(gloss_readme) else 'The glossary'
        lines += [f'**Glossary:** {head}' + (': ' + ' · '.join(link(corpus.item_id(n.path), n.title) for n in terms)
                                              if terms else ''), '']
    books = corpus.books()
    if books:
        lines += [f'**Books read ({len(books)}):** ' + ' · '.join(link(corpus.item_id(p), t) for _, t, p in books), '']
    members = []
    for d, who in sorted(corpus.authors.authors.items(), key=lambda kv: kv[1].get('name', kv[0])):
        mine = [n for n in corpus.notes if n.path.startswith(f'raw-notes/{d}/') and corpus.item_id(n.path)]
        if not mine:
            continue
        index = next((n for n in mine if n.stem.lower() in ('index', 'readme')), None)
        top_note = index or max(mine, key=lambda n: (corpus.inbound.get(n.path, 0), -len(n.path)))
        members.append(f'{link(corpus.item_id(top_note.path), who.get("name") or d)} ({len(mine)})')
    if members:
        lines += ['**Members\' notes:** ' + ' · '.join(members), '']
    lines.append(f'**Everything:** [All posts]({site}{posts_path}/) · [Archive]({site}archive/) · '
                 f'[RSS]({site}feed.xml)')
    return '\n'.join(lines)


def assemble(welcome, featured_block, members, explore):
    return '\n\n'.join(s.strip('\n') for s in (welcome, featured_block, members, explore)) + '\n'


def featured_block_of(content_md):
    """The featured (or series) + did-you-know block of an existing page, verbatim, or None."""
    m = BLOCK_START.search(content_md)
    end = content_md.find(MEMBERS_HEADING)
    if not m or end == -1 or end < m.start():
        return None
    return content_md[m.start():end].strip('\n')


def series_section(series, site):
    """The front page's block on a series day: the post's title, a teaser written here (no AI), a link."""
    import blyg_series as S
    name = S.TYPES[series['type']][0]
    return '\n'.join([
        SERIES_HEADING + name,
        '',
        f"**{link(series['id'], series['title'])}**",
        '',
        safe_generated(series['teaser']),
        '',
        f"{link(series['id'], 'Read today’s post →')} · [Every post in the series]({norm_base(site)}h/{series['type']}/)",
    ])


# ---------------------------------------------------------------- blyg reads

def latest_digest(api, exclude_id=None, pages=DIGEST_SCAN_PAGES):
    """The newest public digest among the most recently updated public items."""
    for n, it in enumerate(api.items(status='public')):
        if n >= pages * 100:
            break
        md = it.get('contentMd') or ''
        if it.get('id') != exclude_id and it.get('status') == 'public' and md.startswith(DIGEST_PREFIX):
            return {'id': it['id'], 'title': md.splitlines()[0].lstrip('# ').strip()}
    return None


def item_title(md, fallback='Untitled post'):
    for line in (md or '').splitlines():
        line = line.strip()
        if not line or line.startswith('!['):
            continue
        line = re.sub(r'^#+\s*', '', line)
        line = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', line)
        line = re.sub(r'[*_`>]', '', line)
        if line:
            return label(line)
    return fallback


def member_posts(api, site, slug, n=MEMBER_POSTS):
    """Newest items filed in the members hopper: [{title, author, url}]."""
    hopper = next((h for h in api.hoppers() if h.get('slug') == slug), None)
    if not hopper:
        log(f'  no hopper /h/{slug}/ yet')
        return []
    origins = None
    out = []
    # Memberships come newest first, each with its held imported item; our own
    # items filed into the hopper (subscription "~own") have none and are read
    # from /items.
    for m in api.memberships(hopper['id']):
        if len(out) >= n:
            break
        sub, rid = m.get('subscriptionId'), m.get('remoteId')
        if sub == OWN_SUBSCRIPTION:
            try:
                own = api.item(rid)
            except BlygError as e:
                if isinstance(e, AuthError):
                    raise
                continue
            if own.get('status') != 'public':
                continue
            out.append({'title': item_title(own.get('contentMd')), 'author': '',
                        'url': f"{site}{'t' if own.get('kind') == 'thread' else 'f'}/{rid}/"})
            continue
        it = m.get('item')
        if not it or it.get('state', 'current') != 'current':
            continue
        if origins is None:
            origins = {s['id']: (norm_base(s.get('origin') or ''), s.get('title') or '') for s in api.subscriptions()}
        origin, sub_title = origins.get(sub, ('', ''))
        author = it.get('author') if isinstance(it.get('author'), dict) else {}
        page = it.get('page')
        if page:
            url = page if re.match(r'https?://', page) else origin + page.lstrip('/')
        else:
            url = f"{origin}{'t' if it.get('kind') == 'thread' else 'f'}/{it.get('remoteId')}/"
        if not url.startswith('http'):
            continue
        out.append({'title': item_title(it.get('contentMd')), 'author': author.get('name') or sub_title, 'url': url})
    return out


LINK_ID = re.compile(r'(?<!!)\[\[([0-9a-z]{26})(?:[ \t]*\|[ \t]*([^\n\]]*))?\]\]')


def unresolved_link_ids(err):
    """Ids named by a publish 400 'one or more references do not resolve'."""
    errors = err.details.get('errors')
    if err.status != 400 or not isinstance(errors, list):
        return set()
    return {m.group(1) for e in errors if isinstance(e, dict)
            for m in LINK_ID.finditer(str(e.get('directive', '')))}


def unlink(content_md, ids):
    return LINK_ID.sub(lambda m: (m.group(2) or '').strip() if m.group(1) in ids else m.group(0), content_md)


# ---------------------------------------------------------------- the run

class FrontPage:
    def __init__(self, corpus, *, api=None, ai=None, site, history, history_path=HISTORY_PATH, front_id=None,
                 slug=DEFAULT_SLUG, blurb_via='tk', dry_run=False, members_only=False, create=False, now=None,
                 save=True, series=True, texts=None):
        self.corpus = corpus
        self.api = api
        self.ai = ai
        self.site = norm_base(site)
        self.history = history
        self.history_path = history_path
        self.front_id = front_id
        self.slug = slug
        self.blurb_via = blurb_via
        self.dry_run = dry_run
        self.members_only = members_only
        self.create = create
        self.now = now or datetime.now(timezone.utc)
        self.today = self.now.date()
        self.save = save
        self.series = series
        self.texts = texts
        self.report = {'ai_calls': 0, 'blyg_generate_calls': 0, 'published': False, 'chosen_by': None, 'blurb': None,
                       'series': None}

    # -- sections that are not chosen
    def posts_path(self):
        if not self.api:
            return 'posts'
        try:
            return (self.api.settings() or {}).get('postsPath') or 'posts'
        except BlygError as e:
            if isinstance(e, AuthError):
                raise
            return 'posts'

    def members(self):
        if not self.api:
            log('  (no BLYG token: member posts and digest not read)')
            return None, []
        digest = latest_digest(self.api, exclude_id=self.front_id)
        posts = member_posts(self.api, self.site, self.slug)
        log(f'  latest digest: {digest["title"] if digest else "none"}; {len(posts)} member post(s)')
        return digest, posts

    # -- choosing
    def choose(self):
        c = self.corpus
        recent = recent_paths(self.history, self.today)
        rng = day_rng(self.today)
        avoid = self.previous_featured_author()
        featured = pick_featured(c, recent, rng, avoid_author=avoid)
        if featured is None:
            raise SystemExit('ERROR: no eligible notes for the front page (all excluded?)')
        authors = sorted(by_author(c, eligible_pool(c, recent)))
        log(f'Authors with eligible notes: {", ".join(authors)}' + (f' (skipping yesterday\'s {avoid})' if avoid else ''))
        log(f'Featured author: {c.author_key(featured)} → {featured.path}')
        cands = shortlist(c, recent, rng=rng, exclude=[featured])
        log(f'Hook shortlist: {len(cands)} candidates')
        for i, n in enumerate(cands, 1):
            log(f'  C{i:02d} {c.score(n):5.2f}  {c.author_key(n):24s} {n.path}')
        pick = None
        if self.ai and cands:
            try:
                text = self.ai.chat(SELECT_SYSTEM, selection_prompt(featured, cands, c), max_tokens=1500)
                pick = validate_selection(parse_json_object(text), cands, featured, c)
                pick['chosen_by'] = 'ai'
            except (AiError, ValueError) as e:
                log(f'  ! AI hooks unusable ({e}); using the deterministic order')
        elif not self.ai:
            log('  no Workers AI credentials; using the deterministic order')
        if pick is None:
            pick = fallback_selection(cands, c, featured)
            pick['chosen_by'] = 'fallback'
        self.report['chosen_by'] = pick['chosen_by']
        log(f"Featured: {pick['featured'].path} (hooks: {pick['chosen_by']})")
        for n, hook in pick['dyk']:
            log(f'  DYK {c.author_key(n):24s} {n.path}: {hook or "(summary line)"}')
        return pick

    def previous_featured_author(self):
        """The author of the most recent featured note before today, or None."""
        days = sorted(d for d in self.history.get('days', {}) if d < self.today.isoformat())
        for d in reversed(days):
            path = self.history['days'][d].get('featured', {}).get('path')
            note = self.corpus.by_path.get(path) if path else None
            if note is not None:
                return self.corpus.author_key(note)
        return None

    def rest_blurb(self, note):
        if not self.ai:
            return None
        try:
            text = self.ai.chat(BLURB_SYSTEM, blurb_prompt(note, self.corpus), max_tokens=600)
        except AiError as e:
            log(f'  ! Workers AI blurb failed: {e}')
            return None
        blurb = clean_blurb(text)
        if not blurb:
            log(f'  ! Workers AI blurb unusable ({words(text)} words)')
        return blurb

    def static_blurb(self, note):
        """The blurb when no blyg generation will happen: Workers AI via impyrt, else the note's words."""
        blurb = self.rest_blurb(note)
        if blurb:
            self.report['blurb'] = 'impyrt'
            return impyrt(blurb)
        self.report['blurb'] = 'excerpt'
        return excerpt_blurb(note, self.corpus)

    # -- writing
    def generate_featured(self, item_id, content, pick, fallback_parts):
        """Fill the featured TK scope (index 0) on the blyg; on failure, rewrite it as impyrt/excerpt."""
        self.report['blyg_generate_calls'] += 1
        try:
            result = self.api.generate(item_id, 0)
            self.report['blurb'] = 'tk'
            log(f"  generated the featured blurb on the blyg ({len(result.get('text') or '')} chars, {result.get('model')})")
            return result['contentMd']
        except BlygError as e:
            if isinstance(e, AuthError):
                raise
            log(f'  ! blyg generation failed ({e}); falling back')
        welcome, members, explore, dyk_md = fallback_parts
        blurb = self.static_blurb(pick['featured'])
        content = assemble(welcome, featured_section(pick['featured'], self.corpus, blurb) + '\n\n' + dyk_md,
                           members, explore)
        self.api.patch_item(item_id, content)
        return content

    def publish(self, item_id, note, content):
        """Publish; a link whose target was withdrawn since becomes plain text (one retry)."""
        try:
            resp = self.api.publish(item_id, note=note, change_category='minor')
        except BlygError as e:
            bad = unresolved_link_ids(e)
            if isinstance(e, AuthError) or not bad:
                raise
            log(f'  ! {len(bad)} link(s) no longer resolve ({", ".join(sorted(bad))}); writing them as plain text')
            self.api.patch_item(item_id, unlink(content, bad))
            resp = self.api.publish(item_id, note=note, change_category='minor')
        if resp.get('warning'):
            log(f"  warning from publish: {resp['warning']}")
        log(f"  published version {resp.get('version')}: {self.site}t/{item_id}/")
        self.report['published'] = True
        return resp

    def run(self):
        mode = 'create' if self.create else 'members-only' if self.members_only else 'daily'
        log(f'World Machines front page — {self.today} ({mode})' + (' — DRY RUN' if self.dry_run else ''))
        existing = None
        if self.front_id and self.api:
            existing = self.api.item(self.front_id)
            log(f"  thread {self.front_id}: status {existing.get('status')}, version {existing.get('version')}, "
                f"dirty {existing.get('dirty')}")
        posts_path = self.posts_path()
        welcome = welcome_section(self.corpus, self.site, posts_path, self.slug)
        digest, posts = self.members()
        members = members_section(digest, posts, self.site, self.slug)
        explore = explore_section(self.corpus, self.site, posts_path)

        kept = featured_block_of(existing.get('contentMd') or '') if existing else None
        chosen_today = bool(self.history.get('days', {}).get(self.today.isoformat(), {}).get('chosen_by'))
        choose = self.create or (not self.members_only and not (chosen_today and kept))
        if not choose and not kept:
            log('  the page has no featured block to keep; nothing to refresh until the daily run')
            return self.report

        pick = series = None
        if choose:
            pick = self.choose()
            dyk_md = dyk_section(pick['dyk'], self.corpus)
            series = self.series_post()
            if series and (series['published'] or self.dry_run):
                block = series_section(series, self.site) + '\n\n' + dyk_md
                use_tk = False
            else:
                use_tk = self.blurb_via == 'tk' and not self.dry_run and self.api is not None
                blurb = tk_blurb(pick['featured'], self.corpus) if use_tk else self.static_blurb(pick['featured'])
                block = featured_section(pick['featured'], self.corpus, blurb) + '\n\n' + dyk_md
        else:
            log('  keeping today\'s featured note and hooks as they are')
            block = kept
            use_tk = False
        content = assemble(welcome, block, members, explore)

        if self.dry_run:
            log('----- front page markdown -----')
            log(content)
            log('-------------------------------')
            if pick and self.blurb_via == 'tk' and not series:
                log('(dry run: the live run generates the featured blurb on the blyg from a TK scope whose source '
                    'is the featured note; the text above is the Workers AI preview of it)')
            return self.report

        if self.create:
            item = self.api.create_thread(content)
            item_id = item['id']
            log(f'  created thread {item_id}')
        else:
            item_id = self.front_id
            if not choose and content == existing.get('contentMd') and not existing.get('dirty') \
                    and existing.get('status') == 'public':
                log('  unchanged; not republishing')
                return self.report
            if content != existing.get('contentMd'):
                self.api.patch_item(item_id, content)
        if use_tk:
            content = self.generate_featured(item_id, content, pick, (welcome, members, explore, dyk_md))

        shown = series if series and series['published'] else None
        note = (f"minor: today's series post is {label(shown['title'], 80)}" if shown
                else f"minor: today's featured note is {label(pick['featured'].title, 80)}" if pick
                else 'minor: member posts refreshed')
        self.publish(item_id, note, content)
        self.report['item_id'] = item_id
        if pick:
            self.record(pick, series)
        if self.create:
            log(f'\nFront page thread id: {item_id}')
            log('Set it as the front page in Studio (Settings → Front page) or with '
                f'PATCH {self.api.base}/settings {{"frontPage": "{item_id}"}}, and set the repo variable '
                f'BLYG_FRONT_ID={item_id}.')
        return self.report

    def series_post(self):
        """Today's series post (blyg_series), built and published before the page; None on a featured-note day.

        Drafts earlier runs left are resumed first, within the run's blyg AI budget. A series that cannot be
        published today (no subject, budget, provider) returns None or an unpublished result, and the page
        shows the featured note instead.
        """
        import blyg_series as S
        stype = S.series_for(self.today)
        if not self.series or self.create:
            return None
        runner = S.Runner(self.corpus, api=self.api, ai=self.ai, site=self.site, history=self.history,
                          today=self.today, dry_run=self.dry_run, texts=self.texts, report=self.report)
        if stype is None:
            if self.api and not self.dry_run:
                runner.resume(runner.recent_series_items(), reserve=1)   # the featured blurb's one call
            return None
        result = runner.run_today(stype)
        if result and not result['published'] and not self.dry_run:
            log('  the series post is not published today; the page shows the featured note')
        return result

    def record(self, pick, series=None):
        c = self.corpus
        entry = {
            'dyk': [{'path': n.path, 'id': c.item_id(n.path)} for n, _ in pick['dyk']],
            'chosen_by': pick['chosen_by'],
            'blurb': self.report['blurb'],
        }
        if not (series and series['published']):
            entry['featured'] = {'path': pick['featured'].path, 'id': c.item_id(pick['featured'].path),
                                 'title': pick['featured'].title}
        series = series or self.report.get('series')
        if series and not self.dry_run:
            entry['series'] = series_record(series)
        self.history.setdefault('days', {})[self.today.isoformat()] = dict(
            sorted(entry.items(), key=lambda kv: ['featured', 'dyk', 'series', 'chosen_by', 'blurb'].index(kv[0])))
        if self.save:
            save_history(self.history, self.history_path, self.today)
            log(f'  history: {self.history_path}')


def series_record(series):
    """A series result as history keeps it."""
    return {k: series.get(k) for k in ('type', 'id', 'title', 'subject', 'subject_title', 'sources', 'author',
                                       'published')}


def run_series_only(stype, corpus, api, ai, site, history, history_path, now, dry_run, save=True):
    """--series-only: one series post (any weekday); the front page is not touched."""
    import blyg_series as S
    today = (now or datetime.now(timezone.utc)).date()
    report = {'blyg_generate_calls': 0, 'series': None, 'published': False}
    runner = S.Runner(corpus, api=api, ai=ai, site=site, history=history, today=today, dry_run=dry_run,
                      report=report)
    result = runner.run_today(stype)
    if result and not dry_run:
        day = history.setdefault('days', {}).setdefault(today.isoformat(), {})
        day['series'] = series_record(result)
        report['published'] = result['published']
        if save:
            save_history(history, history_path, today)
    return report


def main(argv=None, transport=urllib_transport, ai_transport=urllib_transport, corpus=None, now=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dry-run', action='store_true', help='print the markdown and the picks; no blyg writes')
    p.add_argument('--create', action='store_true', help='create and publish the thread; print its id')
    p.add_argument('--members-only', action='store_true', help='keep the featured block; refresh the rest')
    p.add_argument('--id', help='the front-page thread (default: BLYG_FRONT_ID)')
    p.add_argument('--blurb-via', choices=('tk', 'impyrt'), default=os.environ.get('BLYG_FRONT_BLURB') or 'tk')
    p.add_argument('--no-ai', action='store_true', help='never call Workers AI (deterministic picks)')
    p.add_argument('--history', default=str(HISTORY_PATH))
    p.add_argument('--state', default=str(STATE_PATH), help='tools/blyg-import state file (note → item id)')
    p.add_argument('--series-only', metavar='TYPE',
                   choices=('questions', 'concepts', 'books', 'side-by-side', 'terms', 'oracle'),
                   help='build (and unless --dry-run, publish) one series post; the front page is not touched')
    p.add_argument('--no-series', action='store_true', help='featured note every day (no series posts)')
    p.add_argument('--date', help='YYYY-MM-DD: pretend the run happens on this UTC day (with --dry-run only)')
    a = p.parse_args(argv)
    if a.create and a.members_only:
        p.error('--create and --members-only do not go together')
    if a.date:
        if not a.dry_run:
            p.error('--date only goes with --dry-run')
        now = datetime.combine(date.fromisoformat(a.date), datetime.min.time(), timezone.utc).replace(hour=6, minute=30)

    token = (os.environ.get('BLYG_MANAGE_TOKEN') or os.environ.get('BLYG_FRONT_TOKEN')
             or os.environ.get('BLYG_TOKEN'))
    api_base = os.environ.get('BLYG_API_BASE') or DEFAULT_API_BASE
    site = os.environ.get('BLYG_SITE') or site_from_api_base(api_base)
    front_id = a.id or os.environ.get('BLYG_FRONT_ID') or None
    if not token and not a.dry_run:
        sys.exit('ERROR: BLYG_FRONT_TOKEN (or BLYG_TOKEN) is not set. Mint a Studio REST token (Studio → More → '
                 'Client access) with owner:read owner:draft owner:publish.')
    if not a.dry_run and not a.create and not front_id and not a.series_only:
        sys.exit('ERROR: no front-page thread id. Run --create once, then set the repo variable BLYG_FRONT_ID '
                 '(or pass --id).')
    api = BlygApi(api_base, token, transport=transport, dry_run=a.dry_run) if token else None

    ai = None
    acct, ai_token = os.environ.get('CLOUDFLARE_ACCOUNT_ID'), os.environ.get('CF_AI_TOKEN')
    if not a.no_ai and acct and ai_token:
        ai = WorkersAI(acct, ai_token, base=os.environ.get('WORKERS_AI_BASE') or AI_BASE, transport=ai_transport)

    if corpus is None:
        log('Loading the notes corpus')
        corpus = Corpus(state=json.loads(Path(a.state).read_text()).get('items', {}))
        log(f'  {len(corpus.notes)} notes, {len(corpus.state)} blyg items')
    if a.series_only:
        try:
            report = run_series_only(a.series_only, corpus, api, ai, site, load_history(a.history), a.history, now,
                                     a.dry_run)
        except AuthError as e:
            print(f'::error::blyg token refused (HTTP {e.status}); mint a new Studio REST token', file=sys.stderr)
            sys.exit(str(e))
        report['ai_calls'] = ai.calls if ai else 0
        log(f"AI use this run: {report['ai_calls']} Workers AI REST call(s), "
            f"{report['blyg_generate_calls']} blyg TK call(s); published: {report['published']}")
        return report
    front = FrontPage(
        corpus, api=api, ai=ai, site=site, history=load_history(a.history), history_path=a.history,
        front_id=front_id, slug=os.environ.get('BLYG_HOPPER_SLUG') or DEFAULT_SLUG, blurb_via=a.blurb_via,
        dry_run=a.dry_run, members_only=a.members_only, create=a.create, now=now, series=not a.no_series,
    )
    try:
        report = front.run()
    except AuthError as e:
        print(f'::error::blyg token refused (HTTP {e.status}); mint a new Studio REST token', file=sys.stderr)
        sys.exit(str(e))
    except BlygError as e:
        print(f'::error::{e}', file=sys.stderr)
        sys.exit(f'ERROR: {e}')
    report['ai_calls'] = ai.calls if ai else 0
    log(f"AI use this run: {report['ai_calls']} Workers AI REST call(s), "
        f"{report['blyg_generate_calls']} blyg TK call(s); published: {report['published']}")
    return report


if __name__ == '__main__':
    main()
