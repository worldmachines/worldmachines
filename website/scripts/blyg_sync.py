#!/usr/bin/env python3
"""
Collect member hopper posts into the World Machines blyg and publish a digest.

Members propose their WM-related blyg hoppers at worldmachines.org/hoppers;
approved ones are listed by GET https://worldmachines.org/api/hoppers. This
script:

  1. finds out which items each approved hopper holds, one of two ways, and
     logs which one it used per hopper:
       * hopper feed (Studio 0.50+, spec 0.4 §16.12): when the member's
         manifest ({base}blyg.json) lists the hopper with a feed, the WM blyg
         keeps a *hopper subscription* to it (POST /subscriptions with the
         hopper page URL; proposal kind "hopper", then confirm). Its entries
         are L0 rows (an excerpt and a link to the member's item page), and
         the links are the wanted items. Needs Settings → Network → hopper
         feeds on the WM node too: with it off the WM node resolves the
         hopper page as the whole blyg, and this script says so and falls
         back;
       * page scrape (fallback): the hopper's public HTML page, its items'
         permalinks ({blyg base}t/{id}/ or f/{id}/). Used when the member's
         node does not offer the hopper as a feed (Studio before 0.50, or
         hopper feeds off there), when the WM node will not subscribe to it,
         and on the run that creates the hopper subscription (its entries
         arrive with the backfill);
  2. makes the WM blyg subscribe to every blyg those items live on (the whole
     blyg). Hopper-feed entries are excerpts that can never be a [TK] source,
     a quote or a [[link]], so filing and the digest use the whole-blyg copy;
  3. matches each wanted item to the WM blyg's imported copy
     (GET /reading/imported) — items not imported yet wait for the next run;
  3a. puts every approved hopper's own blyg (its `base`) in the WM blyg's
     public blogroll (inBlogroll: true). Only those: a blyg merely linked
     from inside a hopper is subscribed but not blogrolled. Nothing is ever
     removed from the blogroll here;
  4. files the matched items into the WM hopper (default slug `members`). This
     is curation only: they show on blyg.worldmachines.org/h/members/;
  5. writes a [TK] digest thread over the newly filed posts, has the Studio's
     model (Gemma on Workers AI) generate each scope, and publishes it.

Stateless: the WM hopper's membership is the watermark. A run that finds
nothing new files nothing and posts nothing; an item that leaves a member's
hopper is never unfiled here. When generation fails (the shared
AI budget is 20 calls a day), the digest stays a draft and the next run finds
it by its title, files anything it names that is not filed yet, and retries the
missing scopes instead of starting a duplicate.

Usage (from website/):
  python scripts/blyg_sync.py --dry-run          # read-only; print the plan
  python scripts/blyg_sync.py                    # sync, file, digest
  python scripts/blyg_sync.py --no-digest        # sync and file only
  python scripts/blyg_sync.py --blogroll-only    # read /api/hoppers, subscribe to each
                                                 # approved hopper's blyg and hopper feed,
                                                 # blogroll the blyg; no page scraping,
                                                 # filing or digest

Speaks Blygger Studio's private API contract 5.2.0 (Studio 0.51): camelCase
fields, opaque cursor pages, item commands conditional on `expectedRevision`
(a 409 revision-conflict re-reads the item once and retries), errors as
{code, message, details}.

Environment:
  BLYG_TOKEN        Studio REST token (Studio → More → Client access → REST API)
                    with scopes owner:read owner:manage owner:draft owner:publish.
                    Expires after at most 30 days.
  BLYG_API_BASE     default https://blyg.worldmachines.org/api ({mount}/api)
  BLYG_SITE         the WM blyg's public base; default: BLYG_API_BASE minus /api
  BLYG_HOPPER_SLUG  default members
  BLYG_HOPPER_NAME  default "From World Machines members"
  WM_HOPPERS_URL    default https://worldmachines.org/api/hoppers

Stdlib only.
"""
import argparse
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = 'worldmachines-blyg-sync/1.0 (+https://worldmachines.org/hoppers)'
DEFAULT_API_BASE = 'https://blyg.worldmachines.org/api'
DEFAULT_HOPPERS_URL = 'https://worldmachines.org/api/hoppers'
DEFAULT_SLUG = 'members'
DEFAULT_HOPPER_NAME = 'From World Machines members'
DIGEST_PREFIX = '# World Machines digest — '
TOKEN_SCOPES = 'owner:read owner:manage owner:draft owner:publish'

MAX_SOURCES = 6     # sources per TK scope; the server does not truncate them
MAX_SCOPES = 3      # scopes per digest; leftovers stay unfiled for the next run
POLL_WAIT = 45      # seconds to let a forced poll import before reading
WRITE_INTERVAL = 1.1  # delegated tokens share 60 writes/min across grants

# Blygger ids: 26 chars of Crockford-ish base32 (src/identity.ts ID_ALPHABET).
ID_CHARS = '0123456789abcdefghjkmnpqrstvwxyz'
ID_RE = f'[{ID_CHARS}]{{26}}'
PERMALINK = re.compile(rf'^(https?://[^?#]*?/)(t|f)/({ID_RE})/?$')
ITEM_DOC = re.compile(rf'^(https?://[^?#]*?/)items/({ID_RE})\.json$')

HOPPER_FEEDS_OFF = ('the WM node will not subscribe to hopper feeds: turn on Settings → Network → hopper feeds '
                    'on the WM node (it gates subscribing as well as publishing on Studio 0.51). '
                    'Falling back to reading the hopper page.')


def log(msg=''):
    print(msg, flush=True)


# ---------------------------------------------------------------- errors

def error_text(body):
    """The readable part of a private-API error body ({code, message, details?})."""
    if isinstance(body, dict):
        message = body.get('message') or body.get('error')
        code = body.get('code')
        if code and message:
            return f'{code}: {message}'
        return message or code or json.dumps(body)[:300]
    return body


class BlygError(Exception):
    def __init__(self, status, method, path, body):
        self.status, self.method, self.path, self.body = status, method, path, body
        super().__init__(f'{method} {path} → HTTP {status}: {error_text(body)}')

    @property
    def code(self):
        return self.body.get('code') if isinstance(self.body, dict) else None

    @property
    def message(self):
        return (self.body.get('message') or '') if isinstance(self.body, dict) else str(self.body or '')

    @property
    def details(self):
        d = self.body.get('details') if isinstance(self.body, dict) else None
        return d if isinstance(d, dict) else {}


class AuthError(BlygError):
    studio = 'https://blyg.worldmachines.org/studio'

    def __str__(self):
        detail = error_text(self.body)
        return (
            f'\n{"=" * 72}\n'
            f'BLYG_TOKEN was refused: {self.method} {self.path} → HTTP {self.status} ({detail}).\n'
            'Studio REST tokens expire after at most 30 days, and a token missing a\n'
            'scope gets 403. Mint a new one and update the secret:\n'
            f'  1. Open {self.studio} → More → Client access.\n'
            '  2. Create a REST API token with these permissions:\n'
            f'       {TOKEN_SCOPES}\n'
            '  3. gh secret set BLYG_TOKEN --repo worldmachines/worldmachines\n'
            f'{"=" * 72}'
        )


class GenerationFailed(Exception):
    pass


# ---------------------------------------------------------------- HTTP layer

def urllib_transport(method, url, headers, data, timeout=60):
    """(status, headers, bytes) for any HTTP answer; raises only on network errors."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def fetch_text(url, transport=urllib_transport):
    """GET a public page or JSON; raises RuntimeError on a non-200."""
    status, _, body = transport('GET', url, {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/json'}, None)
    if status != 200:
        raise RuntimeError(f'GET {url} → HTTP {status}')
    return body.decode('utf-8', errors='replace')


class BlygApi:
    """Every call to the Studio owner API goes through request().

    Contract 5.2.0 (Studio 0.51). The base is `{mount}/api` (BLYG_API_BASE).
    Collections are cursor-paged (`paged`); item commands carry the item's
    `revision` as `expectedRevision` (`item_command`), which this class
    remembers from every item it reads, creates or changes.
    """

    def __init__(self, base, token, transport=urllib_transport, dry_run=False,
                 write_interval=WRITE_INTERVAL, sleep=time.sleep):
        self.base = base.rstrip('/')
        self.token = token
        self.transport = transport
        self.dry_run = dry_run
        self.write_interval = write_interval
        self.sleep = sleep
        self._last_write = 0.0
        self._revisions = {}  # item id → last revision seen

    def request(self, method, path, body=None, query=None, ok=(200, 201), retry_429=True):
        """JSON request. Returns (status, json). Raises AuthError / BlygError."""
        if method != 'GET' and self.dry_run:
            raise RuntimeError(f'dry run: refusing to send {method} {path}')
        url = self.base + path
        if query:
            query = {k: v for k, v in query.items() if v is not None}
        if query:
            url += '?' + urllib.parse.urlencode(query)
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json',
            'User-Agent': USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        for attempt in range(3):
            if method != 'GET' and self.write_interval:
                wait = self._last_write + self.write_interval - time.monotonic()
                if wait > 0:
                    self.sleep(wait)
                self._last_write = time.monotonic()
            status, resp_headers, raw = self.transport(method, url, headers, data)
            try:
                payload = json.loads(raw.decode() or 'null') if raw else None
            except ValueError:
                payload = {'code': 'internal', 'message': raw[:300].decode(errors='replace')}
            if status in (401, 403):
                err = AuthError(status, method, path, payload)
                err.studio = site_from_api_base(self.base) + 'studio'
                raise err
            if status == 429 and retry_429 and attempt < 2:
                retry = _retry_after(resp_headers)
                log(f'  rate limited on {method} {path}; retrying in {retry}s')
                self.sleep(retry)
                continue
            if status not in ok:
                raise BlygError(status, method, path, payload)
            return status, payload
        raise BlygError(status, method, path, payload)

    def get(self, path, **query):
        return self.request('GET', path, query=query or None)[1]

    def paged(self, path, limit=100, **filters):
        """Yield every row of a cursor-paged collection ({items, page: {nextCursor}}).

        A relevant change on the server expires the cursor (409
        cursor-expired); the walk then restarts from the first page, skipping
        rows it has already yielded, at most twice.
        """
        seen, cursor, restarts = set(), None, 0
        for _ in range(10000):
            try:
                page = self.get(path, limit=limit, cursor=cursor, **filters)
            except BlygError as e:
                if e.status == 409 and e.code == 'cursor-expired' and cursor and restarts < 2:
                    restarts += 1
                    log(f'  {path}: the list changed while it was being read; starting it again')
                    cursor = None
                    continue
                raise
            for row in page.get('items') or []:
                key = _row_key(row)
                if key in seen:
                    continue
                seen.add(key)
                yield row
            cursor = (page.get('page') or {}).get('nextCursor')
            if not cursor:
                return

    # -- reads
    def subscriptions(self):
        return list(self.paged('/subscriptions'))

    def hoppers(self):
        return list(self.paged('/hoppers'))

    def hopper(self, hopper_id):
        """{hopper, total, sourceCount}; members come from memberships()."""
        return self.get(f'/hoppers/{q(hopper_id)}')

    def memberships(self, hopper_id):
        """Yield hopper memberships, newest added first, each with its held imported `item` (or null)."""
        return self.paged(f'/hoppers/{q(hopper_id)}/memberships')

    def items(self, status=None):
        """Yield items, most recently updated first; `status` is draft, public or withdrawn."""
        return self.paged('/items', status=status)

    def item(self, item_id):
        item = self.get(f'/items/{q(item_id)}')
        self._note_revision(item_id, item)
        return item

    def settings(self):
        return self.get('/settings')

    def imported(self, limit=100):
        """Yield /reading/imported rows, newest observed first."""
        return self.paged('/reading/imported', limit=limit)

    def reading(self, sub=None, limit=50):
        """Yield the imported entries of /reading (optionally one subscription's), flattened."""
        for row in self.paged('/reading', limit=limit, sub=sub):
            entry = row.get('imported') if isinstance(row.get('imported'), dict) else None
            if entry:
                yield entry

    # -- writes
    def set_in_blogroll(self, sub_id, value=True):
        return self.request('PATCH', f'/subscriptions/{q(sub_id)}', {'inBlogroll': value})[1]

    def subscribe(self, url, confirm=True, backfill=True, whole_blyg=None):
        """(status, body). 201 created; 200 a proposal (always without confirm); 409 already subscribed."""
        body = {'url': url, 'confirm': confirm}
        if confirm:
            body['backfill'] = backfill
        if whole_blyg is not None:
            body['wholeBlyg'] = whole_blyg
        return self.request('POST', '/subscriptions', body, ok=(200, 201, 409, 422))

    def poll(self):
        return self.request('POST', '/subscriptions/poll')[1]

    def create_hopper(self, name):
        return self.request('POST', '/hoppers', {'name': name})[1]

    def patch_hopper(self, hopper_id, **fields):
        return self.request('PATCH', f'/hoppers/{q(hopper_id)}', fields)[1]

    def file(self, hopper_id, sub_id, remote_id):
        return self.request('PUT', f'/hoppers/{q(hopper_id)}/items/{q(sub_id)}/{q(remote_id)}')[1]

    def create_thread(self, content_md):
        item = self.request('POST', '/items', {'kind': 'thread', 'contentMd': content_md})[1]
        self._note_revision(item.get('id'), item)
        return item

    def patch_item(self, item_id, content_md):
        return self.item_command('PATCH', item_id, f'/items/{q(item_id)}', {'contentMd': content_md})

    def generate(self, item_id, scope):
        # 429 here is the daily AI budget, not a rate limit: never retry it.
        return self.item_command('POST', item_id, f'/items/{q(item_id)}/generate', {'scope': scope},
                                 ok=(200,), retry_429=False)

    def publish(self, item_id, note=None, change_category=None):
        body = {}
        if note is not None:
            body['note'] = note
        if change_category is not None:
            body['changeCategory'] = change_category
        return self.item_command('POST', item_id, f'/items/{q(item_id)}/publish', body)

    def item_command(self, method, item_id, path, body, **kw):
        """An item write with `expectedRevision`. A stale revision (409
        revision-conflict: the item changed since we read it) re-reads the item
        once and retries; a second conflict raises."""
        for attempt in (0, 1):
            rev = self._revisions.get(item_id)
            if rev is None:
                rev = self.item(item_id).get('revision')
            try:
                _, out = self.request(method, path, dict(body, expectedRevision=rev), **kw)
            except BlygError as e:
                if attempt == 0 and e.status == 409 and e.code == 'revision-conflict':
                    log(f'  {method} {path}: item {item_id} changed since revision {rev}; re-reading and retrying once')
                    self._revisions.pop(item_id, None)
                    continue
                raise
            self._note_revision(item_id, out)
            return out

    def _note_revision(self, item_id, payload):
        if item_id and isinstance(payload, dict) and isinstance(payload.get('revision'), int):
            self._revisions[item_id] = payload['revision']


def _row_key(row):
    if not isinstance(row, dict):
        return json.dumps(row, sort_keys=True)
    if row.get('key'):
        return ('key', row['key'])
    if row.get('remoteId') is not None:
        return ('imported', row.get('hopperId'), row.get('subscriptionId'), row['remoteId'])
    return ('id', row.get('id'))


def q(segment):
    return urllib.parse.quote(str(segment), safe='')


def _retry_after(headers):
    for k, v in (headers or {}).items():
        if k.lower() == 'retry-after':
            try:
                return max(1, min(int(float(v)), 120))
            except ValueError:
                break
    return 30


# ---------------------------------------------------------------- URL helpers

def norm_base(url):
    """Canonical blyg base: lowercase scheme+host, path ending in '/'."""
    p = urllib.parse.urlsplit(url.strip())
    path = p.path if p.path.endswith('/') else p.path + '/'
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, '', ''))


def parse_permalink(url):
    """(base, kind, id) for an item permalink, else None. Version links (…/vN/) are not permalinks."""
    p = urllib.parse.urlsplit(url)
    m = PERMALINK.match(urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, '', '')))
    if not m:
        return None
    return norm_base(m.group(1)), m.group(2), m.group(3)


def parse_item_link(url):
    """(base, kind, id) for a hopper-feed entry's link, else None.

    A hopper feed links each entry to the item's declared `page` (Studio:
    {base}t/{id}/ or f/{id}/), else to its item document {base}items/{id}.json,
    whose kind is unknown (None).
    """
    if not url:
        return None
    hit = parse_permalink(url)
    if hit:
        return hit
    p = urllib.parse.urlsplit(url)
    m = ITEM_DOC.match(urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, '', '')))
    if not m:
        return None
    return norm_base(m.group(1)), None, m.group(2)


def item_ref(base, kind, item_id):
    return f'{base}{kind}/{item_id}/' if kind else f'{base}items/{item_id}.json'


def site_from_api_base(api_base):
    base = api_base.rstrip('/')
    if base.endswith('/api'):
        base = base[:-4]
    return norm_base(base)


# ---------------------------------------------------------------- WM hopper list

def parse_wm_hoppers(payload):
    """Approved hoppers as [{canonical, base, name, handle}] from /api/hoppers.

    Accepts the current shape ({hoppers: [{url, name, handle, title, ...}]})
    and the planned one, which adds `canonical` and `base`.
    """
    rows = payload.get('hoppers') if isinstance(payload, dict) else payload
    out = []
    for h in rows or []:
        canonical = h.get('canonical') or h.get('url')
        if not canonical:
            continue
        base = h.get('base')
        if not base:
            m = re.match(r'^(.*?)/h/[^/]+/?$', urllib.parse.urlsplit(canonical)._replace(query='', fragment='').geturl())
            if not m:
                log(f'  ! skipping hopper with no /h/<slug> path: {canonical}')
                continue
            base = m.group(1)
        if not canonical.endswith('/'):
            canonical += '/'
        out.append({'canonical': canonical, 'base': norm_base(base),
                    'name': h.get('name') or '', 'handle': h.get('handle') or ''})
    return out


# ---------------------------------------------------------------- hopper page scraping

ARTICLE = re.compile(r'<article\b[^>]*>(.*?)</article>', re.S | re.I)
NAV = re.compile(r'<nav\b.*?</nav>', re.S | re.I)
HREF = re.compile(r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.S | re.I)
SOURCE_ATTRIBUTION = re.compile(r'<p class="provenance">from <a\b.*?</p>', re.S | re.I)
OWN_LINK = re.compile(r'<a class="permalink" href="([^"]*)"|<p class="read-more"><a href="([^"]*)"', re.I)
VERSION_LINE = re.compile(r'data-item="([^"]+)" data-kind="([tf])"[^>]*?data-mount="([^"]*)"', re.I)


def _abs(href, page_url):
    return urllib.parse.urljoin(page_url, htmllib.unescape(href))


def _article_member(article, page_url):
    """The one item an <article> on a Blygger Studio hopper page stands for."""
    # Imported member: the card ends with "from <blyg> — source ↗". Only the
    # last attribution counts; earlier ones belong to quotes inside the body.
    attributions = SOURCE_ATTRIBUTION.findall(article)
    if attributions:
        for href, text in reversed(HREF.findall(attributions[-1])):
            hit = parse_permalink(_abs(href, page_url))
            if hit:
                return hit
        return None  # an L0 or withdrawn item: no blyg permalink to follow
    # The curator's own item: its permalink, "read the thread" link, or version line.
    for m in OWN_LINK.finditer(article):
        hit = parse_permalink(_abs(m.group(1) or m.group(2), page_url))
        if hit:
            return hit
    m = VERSION_LINE.search(article)
    if m:
        return parse_permalink(_abs(f'{m.group(3)}/{m.group(2)}/{m.group(1)}/', page_url))
    return None


def extract_items(page_html, page_url):
    """Ordered, de-duplicated (base, kind, id) items a hopper page shows.

    Blygger Studio renders one <article> per member; reading those avoids the
    site chrome (nav "Pages" links) and links inside post bodies. Other
    clients' pages fall back to every item permalink outside <nav>.
    """
    found = []
    articles = ARTICLE.findall(page_html)
    if articles:
        for a in articles:
            hit = _article_member(a, page_url)
            if hit:
                found.append(hit)
    else:
        for href, _ in HREF.findall(NAV.sub('', page_html)):
            hit = parse_permalink(_abs(href, page_url))
            if hit:
                found.append(hit)
    seen, out = set(), []
    for base, kind, item_id in found:
        if (base, item_id) not in seen:
            seen.add((base, item_id))
            out.append((base, kind, item_id))
    return out


# ---------------------------------------------------------------- TK digest

TK_SCOPE = re.compile(r'\[TK\](.*?)\[/TK\]', re.S)
SOURCE_REF = re.compile(rf'!\[\[({ID_RE})(?:[ \t]*\|[^\n\]]*)?\]\]')
LINK_REF = re.compile(rf'(?<!!)\[\[({ID_RE})(?:[ \t]*\|[^\n\]]*)?\]\]')


def tk_scopes(content_md):
    """[(index, has_output, source_ids)] — mirrors studio src/tk.ts parseScopes for what we write."""
    out = []
    for i, m in enumerate(TK_SCOPE.finditer(content_md)):
        body = m.group(1)
        instr = body.split('[=]', 1)[0]
        out.append((i, '[=]' in body, SOURCE_REF.findall(instr)))
    return out


def referenced_ids(content_md):
    seen, out = set(), []
    for m in re.finditer(rf'\[\[({ID_RE})', content_md):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def clean_label(text, limit=100):
    """One line, no TK/bracket grammar, short."""
    text = re.sub(r'[\[\]]', '', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def post_title(row):
    md = row.get('contentMd') or ''
    for line in md.splitlines():
        line = line.strip()
        if not line or line.startswith('!['):
            continue
        line = re.sub(r'^#+\s*', '', line)
        line = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', line)  # [text](url) → text
        line = re.sub(r'[*_`>]', '', line)
        if line:
            return clean_label(line, 90)
    return 'Untitled post'


def post_author(row):
    author = row.get('author') or {}
    return clean_label(author.get('name') or row.get('subscriptionTitle') or row.get('origin') or 'unknown', 60)


def post_url(row):
    if row.get('sourceUrl'):
        return row['sourceUrl']
    page = row.get('page')
    origin = row.get('origin') or ''
    if page:
        return page if re.match(r'https?://', page) else origin + page.lstrip('/')
    return f"{origin}{'t' if row.get('kind') == 'thread' else 'f'}/{row['remoteId']}/"


def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def digest_title(now):
    return f"{DIGEST_PREFIX}{now:%Y-%m-%d} ({'morning' if now.hour < 12 else 'evening'})"


def scope_instruction(rows, part, parts):
    who = '; '.join(f'"{post_title(r)}" by {post_author(r)}' for r in rows)
    span = f'This is part {part} of {parts} of the digest; cover only the posts given here. ' if parts > 1 else ''
    refs = ' '.join(f"![[{r['remoteId']}]]" for r in rows)
    return (
        f'Write a synthesis of {len(rows)} new post{"s" if len(rows) != 1 else ""} by World Machines members, '
        f'for the other members. {span}The posts are: {who}. '
        'In three to five short paragraphs of plain prose: name the threads the posts share; '
        'say where they disagree or pull in different directions; point out new ideas worth following up; '
        'and end by recommending which post to read first, and why. '
        "Credit every idea to its author by name. Use only what the posts say, and don't invent claims. "
        'No headings, lists, links or quotations longer than a sentence. '
        f'{refs}'
    )


def build_digest(rows, now, hopper_url, max_sources=MAX_SOURCES, hopper_name=DEFAULT_HOPPER_NAME):
    """Markdown for the digest thread: intro, one TK scope per ≤max_sources sources, the post list."""
    sources = [r for r in rows if not r.get('l0') and not r.get('withdrawn')]
    groups = chunk(sources, max_sources)
    authors = sorted({post_author(r) for r in rows})
    lines = [
        digest_title(now),
        '',
        f'{len(rows)} new post{"s" if len(rows) != 1 else ""} from '
        f'{", ".join(authors)} reached the [{hopper_name}]({hopper_url}) collection. '
        "The synthesis below is machine-written from the posts themselves; the originals are listed after it.",
        '',
    ]
    for i, g in enumerate(groups, 1):
        if len(groups) > 1:
            lines += [f'## Synthesis, part {i} of {len(groups)}', '']
        else:
            lines += ['## Synthesis', '']
        lines += [f'[TK]{scope_instruction(g, i, len(groups))}[/TK]', '']
    lines += ['## The new posts', '']
    for r in rows:
        title = post_title(r)
        if r.get('l0') or r.get('withdrawn'):
            lines.append(f'- [{title}]({post_url(r)}) — {post_author(r)}')
        else:
            lines.append(f"- [[{r['remoteId']} | {title}]] — {post_author(r)}")
    return '\n'.join(lines) + '\n'


def drop_source(content_md, source_id):
    """Remove a source that no longer resolves; drop a scope left with none."""
    def fix(m):
        body = re.sub(rf'\s*!\[\[{source_id}(?:[ \t]*\|[^\n\]]*)?\]\]', '', m.group(1))
        instr = body.split('[=]', 1)[0]
        return f'[TK]{body}[/TK]' if SOURCE_REF.search(instr) else ''
    content_md = TK_SCOPE.sub(fix, content_md)
    # Its entry in the post list goes from a link to plain text.
    return re.sub(rf'(?<!!)\[\[{source_id}(?:[ \t]*\|[ \t]*([^\n\]]*))?\]\]',
                  lambda m: (m.group(1) or source_id).strip(), content_md)


# ---------------------------------------------------------------- the run

class Sync:
    def __init__(self, api, *, fetch=fetch_text, site=None, slug=DEFAULT_SLUG, hopper_name=DEFAULT_HOPPER_NAME,
                 hoppers_url=DEFAULT_HOPPERS_URL, dry_run=False, digest=True, blogroll_only=False,
                 max_sources=MAX_SOURCES, max_scopes=MAX_SCOPES, poll_wait=POLL_WAIT, sleep=time.sleep,
                 now=None):
        self.api = api
        self.fetch = fetch
        self.site = norm_base(site or site_from_api_base(api.base))
        self.slug = slug
        self.hopper_name = hopper_name
        self.hoppers_url = hoppers_url
        self.dry_run = dry_run
        self.digest = digest
        self.blogroll_only = blogroll_only
        self.max_sources = max_sources
        self.max_scopes = max_scopes
        self.poll_wait = poll_wait
        self.sleep = sleep
        self.now = now or datetime.now(timezone.utc)
        self.plan = []  # what a dry run would have done
        self._imported = None
        self._all_subs = None  # every subscription, hopper subscriptions included
        self._subs = None  # {normalized origin: whole-blyg subscription} after ensure_subscriptions
        self._hopper_feeds_setting = None
        self._warned_setting = False

    def act(self, description):
        """True when the action should happen; in a dry run, record it instead."""
        if self.dry_run:
            self.plan.append(description)
            log(f'  [dry-run] would {description}')
            return False
        log(f'  {description}')
        return True

    # 1: the member hoppers
    def approved_hoppers(self):
        log(f'Reading approved hoppers from {self.hoppers_url}')
        hoppers = parse_wm_hoppers(json.loads(self.fetch(self.hoppers_url)))
        log(f'  {len(hoppers)} approved hopper(s)')
        return hoppers

    def hopper_bases(self, hoppers):
        """The approved hoppers' own blygs, minus ours."""
        return {h['base'] for h in hoppers} - {self.site}

    def all_subscriptions(self):
        if self._all_subs is None:
            self._all_subs = self.api.subscriptions()
        return self._all_subs

    def whole_blyg_subscriptions(self):
        """{normalized origin: subscription}, hopper subscriptions excluded: one shares its blyg's origin."""
        return {norm_base(s['origin']): s for s in self.all_subscriptions() if not s.get('hopperFeedUrl')}

    def hopper_subscriptions(self):
        return {s['hopperFeedUrl']: s for s in self.all_subscriptions() if s.get('hopperFeedUrl')}

    # 1a: hopper feeds
    def offered_feed(self, h):
        """(feed URL, None) when the member's manifest lists this hopper with a feed, else (None, why)."""
        manifest_url = h['base'] + 'blyg.json'
        try:
            manifest = json.loads(self.fetch(manifest_url))
        except Exception as e:  # unreadable or not JSON: the page is still there to scrape
            return None, f'could not read {manifest_url} ({e})'
        entries = manifest.get('hoppers') if isinstance(manifest, dict) else None
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get('page'), str):
                continue
            if norm_base(urllib.parse.urljoin(h['base'], entry['page'])) != norm_base(h['canonical']):
                continue
            if isinstance(entry.get('feed'), str) and entry['feed']:
                return urllib.parse.urljoin(h['base'], entry['feed']), None
            return None, 'its blyg lists the hopper without a feed'
        return None, ("its blyg does not offer it as a feed (Studio before 0.50, or Settings → Network → "
                      "hopper feeds off on that blyg)")

    def wm_hopper_feeds(self):
        """The WM node's own hopperFeeds setting: True, False, or None when unreadable."""
        if self._hopper_feeds_setting is None:
            try:
                value = (self.api.settings() or {}).get('hopperFeeds')
            except BlygError as e:
                if isinstance(e, AuthError):
                    raise
                log(f'  ! could not read the WM settings: {e}')
                return None
            self._hopper_feeds_setting = value if isinstance(value, bool) else None
        return self._hopper_feeds_setting

    def warn_setting_off(self):
        if not self._warned_setting:
            self._warned_setting = True
            log(f'  ! {HOPPER_FEEDS_OFF}')

    def _find_hopper_sub(self, feed):
        self._all_subs = None  # re-read: it was just created, or someone else created it
        return self.hopper_subscriptions().get(feed)

    def ensure_hopper_subscriptions(self, hoppers):
        """{hopper canonical: route}. A route is {'path': 'feed', 'sub': …} when the
        hopper's items can be read from a hopper subscription now, else
        {'path': 'scrape', 'why': …}. Creates the hopper subscription when it
        is missing and the member's node offers one."""
        routes = {}
        have = self.hopper_subscriptions()
        for h in hoppers:
            c = h['canonical']
            if h['base'] == self.site:
                routes[c] = {'path': 'scrape', 'why': 'a hopper on this blyg'}
                continue
            feed, why = self.offered_feed(h)
            if not feed:
                routes[c] = {'path': 'scrape', 'why': why}
                continue
            sub = have.get(feed)
            if not sub:
                sub, why = self._subscribe_hopper(h, feed)
                if not sub:
                    routes[c] = {'path': 'scrape', 'why': why}
                    continue
                have[feed] = sub
                if sub.get('_new'):
                    routes[c] = {'path': 'scrape', 'sub': sub,
                                 'why': 'hopper subscription just created; its entries arrive with the backfill'}
                    continue
            if sub.get('status') == 'paused':
                flags = ', '.join(f.get('type', '?') for f in sub.get('flags') or [] if isinstance(f, dict))
                routes[c] = {'path': 'scrape', 'sub': sub,
                             'why': f"hopper subscription {sub.get('id')} is paused{f' ({flags})' if flags else ''}"}
            elif not sub.get('lastPollAt'):
                routes[c] = {'path': 'scrape', 'sub': sub,
                             'why': f"hopper subscription {sub.get('id')} has not been polled yet"}
            else:
                routes[c] = {'path': 'feed', 'sub': sub}
        return routes

    def _subscribe_hopper(self, h, feed):
        """(subscription, None) or (None, why). Asks for the proposal first, so
        a WM node that would subscribe to the whole blyg instead is caught
        before anything is created. The WM node's own hopperFeeds setting is
        read first (owner:read), so a node with it off is not sent a proposal
        every run; the proposal's kind is still checked in case it is on but
        the node resolves the page differently."""
        c = h['canonical']
        if self.wm_hopper_feeds() is False:
            self.warn_setting_off()
            return None, 'hopper feeds are off on the WM node'
        if self.dry_run:
            self.act(f'subscribe to the hopper feed {feed} ({c})')
            return None, 'dry run: the hopper subscription is not created'
        log(f'  hopper {c} is offered as a feed ({feed}); asking the WM node for a hopper subscription')
        status, body = self.api.subscribe(c, confirm=False)
        if status == 409:
            sub = self._find_hopper_sub(feed)
            if sub:
                log(f"    already subscribed: {sub.get('title')} ({sub.get('id')})")
                return sub, None
            return None, f'the WM node says already subscribed ({error_text(body)}), but no hopper subscription has that feed'
        if status != 200:
            return None, f'could not resolve the hopper page ({status}: {error_text(body)})'
        if body.get('kind') != 'hopper':
            if self.wm_hopper_feeds() is False:
                self.warn_setting_off()
                return None, 'hopper feeds are off on the WM node'
            log(f"  ! the WM node resolved {c} as {body.get('kind')} ({body.get('title')}), not as a hopper: "
                'check Settings → Network → hopper feeds on the WM node. Reading the page instead.')
            return None, f"the WM node resolved the hopper page as {body.get('kind')}, not as a hopper"
        offered = (body.get('hopper') or {}).get('feedUrl') or body.get('feedUrl')
        if offered and offered != feed:
            log(f'    note: the WM node resolved the feed as {offered} (the manifest says {feed})')
        if not self.act(f"subscribe to the hopper {body.get('title')} ({offered or feed})"):
            return None, 'not subscribed'
        status, body = self.api.subscribe(c, confirm=True)
        if status == 201:
            log(f"    subscribed: {body.get('title')} ({body.get('id')}), feed {body.get('hopperFeedUrl')}")
            sub = dict(body, _new=True)
            self.all_subscriptions().append(body)
            return sub, None
        if status == 409:
            sub = self._find_hopper_sub(offered or feed)
            if sub:
                return sub, None
        return None, f'could not subscribe to the hopper ({status}: {error_text(body)})'

    def hopper_feed_items(self, sub):
        """(base, kind, id) for each entry of a hopper subscription, newest first."""
        found = []
        for entry in self.api.reading(sub=sub['id']):
            if entry.get('subscriptionId') not in (None, sub['id']):
                continue
            hit = parse_item_link(entry.get('sourceUrl'))
            if hit:
                found.append(hit)
            else:
                log(f"    entry {entry.get('remoteId')} links to {entry.get('sourceUrl')!r}, not a blyg item; skipped")
        return found

    def wanted_items(self, hoppers, routes=None):
        routes = routes or {}
        wanted, seen = [], set()
        for h in hoppers:
            route = routes.get(h['canonical']) or {'path': 'scrape', 'why': 'no hopper feed checked'}
            if route['path'] == 'feed':
                sub = route['sub']
                try:
                    items = self.hopper_feed_items(sub)
                except BlygError as e:
                    if isinstance(e, AuthError):
                        raise
                    log(f"  ! could not read hopper subscription {sub.get('id')}: {e}")
                    continue
                log(f"  {h['canonical']}: {len(items)} item(s) [hopper feed {sub.get('hopperFeedUrl')}]")
            else:
                try:
                    page = self.fetch(h['canonical'])
                except Exception as e:  # one unreachable blyg must not stop the others
                    log(f"  ! could not read {h['canonical']}: {e}")
                    continue
                items = extract_items(page, h['canonical'])
                log(f"  {h['canonical']}: {len(items)} item(s) [page scrape: {route.get('why')}]")
            for base, kind, item_id in items:
                if base == self.site:
                    continue  # already ours
                if (base, item_id) not in seen:
                    seen.add((base, item_id))
                    wanted.append({'base': base, 'kind': kind, 'id': item_id, 'hopper': h['canonical'],
                                   'via': route['path']})
        return wanted

    # 2: whole-blyg subscriptions
    def ensure_subscriptions(self, bases, poll=True):
        subs = self.whole_blyg_subscriptions()
        self._subs = subs
        have = set(subs)
        new = 0
        for base in sorted(bases):
            if base in have:
                continue
            if not self.act(f'subscribe to {base}'):
                continue
            # The base, never a hopper page: a hopper URL could resolve to a hopper subscription.
            status, body = self.api.subscribe(base)
            if status == 201:
                log(f"    subscribed: {body.get('title')} ({body.get('id')})")
                self.all_subscriptions().append(body)
                subs[base] = body
                if body.get('origin'):
                    subs.setdefault(norm_base(body['origin']), body)
                new += 1
            elif status == 200:
                log(f'    the blyg proposed a subscription but did not create it; confirm it in Studio: {body}')
            elif status == 409:
                log(f'    already subscribed ({error_text(body)})')
            else:
                log(f'    ! could not subscribe ({status}): {error_text(body)}')
        if new and poll and self.act('force a poll of all subscriptions'):
            log(f"    polling {self.api.poll().get('polling')} subscription(s); waiting {self.poll_wait}s")
            self.sleep(self.poll_wait)
        return new

    # 3a: blogroll
    def ensure_blogroll(self, bases):
        """Set inBlogroll on the whole-blyg subscription for each base. Never clears it.

        `bases` are the approved hoppers' own blygs. Runs after
        ensure_subscriptions, whose subscription list (plus anything it just
        created) is what we match against. Returns the bases added (or, in a
        dry run, that would be added).
        """
        subs = self._subs if self._subs is not None else self.whole_blyg_subscriptions()
        added = []
        for base in sorted(bases):
            sub = subs.get(base)
            if not sub:
                if self.dry_run:
                    self.act(f'add {base} to the blogroll (once subscribed)')
                    added.append(base)
                else:
                    log(f'  ! {base} has no subscription with that origin, so it cannot be blogrolled '
                        '(subscribed under another origin, or subscribing failed). Check Studio → Reading.')
                continue
            if sub.get('inBlogroll'):
                log(f'  already in the blogroll: {base}')
                continue
            if sub.get('status') == 'paused':
                log(f'  note: {base} is paused; the public blogroll omits paused subscriptions')
            if self.act(f"add {base} to the blogroll (subscription {sub.get('id')})"):
                updated = self.api.set_in_blogroll(sub['id'], True)
                sub['inBlogroll'] = bool((updated or {}).get('inBlogroll', True))
            added.append(base)
        return added

    # 4: imported rows
    def imported_index(self, want_ids=None):
        """{remoteId: [row, …]}. Stops early once every wanted id is seen."""
        if self._imported is not None and not want_ids:
            return self._imported
        index, pending = {}, set(want_ids or ())
        for row in self.api.imported():
            index.setdefault(row['remoteId'], []).append(row)
            pending.discard(row['remoteId'])
            if want_ids and not pending:
                break
        self._imported = index
        return index

    def match(self, wanted, index):
        hopper_subs = {s['id'] for s in self.all_subscriptions() if s.get('hopperFeedUrl')}
        matched, missing = [], []
        for w in wanted:
            rows = [r for r in index.get(w['id']) or [] if r.get('subscriptionId') not in hopper_subs and not r.get('l0')]
            same = [r for r in rows if norm_base(r.get('origin') or '') == w['base']]
            pick = same or (rows if len(rows) == 1 else [])
            if pick:
                matched.append(pick[0])
            else:
                missing.append(w)
        return matched, missing

    # 5: the WM hopper
    def ensure_hopper(self):
        for h in self.api.hoppers():
            if h.get('slug') == self.slug:
                if not h.get('public'):
                    log(f'  ! hopper /h/{self.slug}/ is private; make it public in Studio for the page to show')
                return h
        if not self.act(f'create hopper "{self.hopper_name}" at /h/{self.slug}/'):
            return None
        # The slug comes from the name and freezes when the hopper goes public,
        # so: create as the slug, publish (freezes it), then rename.
        h = self.api.create_hopper(self.slug)
        if h.get('slug') != self.slug:
            log(f"  ! the server gave slug {h.get('slug')!r}, not {self.slug!r} (a clash?); using it")
        h = self.api.patch_hopper(h['id'], public=True)
        if self.hopper_name != self.slug:
            h = self.api.patch_hopper(h['id'], name=self.hopper_name)
        return h

    def membership(self, hopper):
        if not hopper:
            return set()
        return {(m['subscriptionId'], m['remoteId']) for m in self.api.memberships(hopper['id'])}

    def file(self, hopper, rows, members):
        filed = []
        for r in rows:
            key = (r['subscriptionId'], r['remoteId'])
            if key in members:
                continue
            if self.act(f"file {r['remoteId']} ({post_author(r)}: {post_title(r)}) into /h/{self.slug}/"):
                self.api.file(hopper['id'], *key)
                members.add(key)
            filed.append(r)
        return filed

    # 6: digest
    def unfinished_digest(self):
        drafts = [i for i in self.api.items(status='draft')
                  if i.get('status') == 'draft' and (i.get('contentMd') or '').startswith(DIGEST_PREFIX)]
        return sorted(drafts, key=lambda i: i.get('created') or '')[0] if drafts else None

    def generate_and_publish(self, item):
        content = item['contentMd']
        item_id = item['id']
        dropped = set()
        if self.dry_run:
            for idx, has_output, _ in tk_scopes(content):
                if not has_output:
                    self.act(f'generate scope {idx} of digest {item_id}')
            self.act(f'publish digest {item_id}')
            return None
        while True:
            todo = [i for i, has_output, _ in tk_scopes(content) if not has_output]
            if not todo:
                break
            idx = todo[0]
            log(f'  generate scope {idx} of digest {item_id}')
            try:
                result = self.api.generate(item_id, idx)
            except BlygError as e:
                if isinstance(e, AuthError):
                    raise
                bad = e.details.get('id')
                if e.status == 400 and 'unresolvable source' in e.message and bad and bad not in dropped:
                    log(f"    source {bad} no longer resolves ({e.details.get('reason')}); dropping it from the digest")
                    dropped.add(bad)
                    content = drop_source(content, bad)
                    self.api.patch_item(item_id, content)
                    continue
                if e.status == 429:
                    raise GenerationFailed(
                        f'the daily AI budget is spent (HTTP 429: {e.message}). The digest {item_id} '
                        'stays a draft; the next run retries it.') from e
                if e.status == 502:
                    raise GenerationFailed(
                        f'the model provider failed (HTTP 502: {e.message}); a provider error still counts '
                        f'against the AI budget (a config error does not). The digest {item_id} stays a draft; the next run retries it.') from e
                raise GenerationFailed(f'generation failed: {e}. The digest {item_id} stays a draft.') from e
            content = result['contentMd']
            log(f"    generated {len(result.get('text') or '')} chars with {result.get('model')}")
        if not tk_scopes(content) and not referenced_ids(content):
            log(f'  ! digest {item_id} has nothing left to publish; leaving it as a draft')
            return None
        if self.act(f'publish digest {item_id}'):
            resp = self.api.publish(item_id)
            if resp.get('warning'):
                log(f"    warning from publish: {resp['warning']}")
            log(f"    published version {resp.get('version')}: {self.site}t/{item_id}/")
            return resp
        return None

    def resume(self, hopper, members):
        """Finish a digest a previous run left as a draft. Returns True if one was found."""
        draft = self.unfinished_digest()
        if not draft:
            return False
        title = draft['contentMd'].splitlines()[0]
        log(f"Resuming unfinished digest {draft['id']}: {title}")
        ids = referenced_ids(draft['contentMd'])
        index = self.imported_index(ids)
        hopper_subs = {s['id'] for s in self.all_subscriptions() if s.get('hopperFeedUrl')}
        rows = []
        for i in ids:
            held = [r for r in index.get(i) or [] if r.get('subscriptionId') not in hopper_subs]
            if held:
                rows.append(held[0])
        if hopper:
            self.file(hopper, rows, members)
        self.generate_and_publish(draft)
        return True

    def run(self):
        log(f'World Machines blyg: {self.site} (API {self.api.base})' + (' — DRY RUN' if self.dry_run else '')
            + (' — blogroll only' if self.blogroll_only else ''))
        hoppers = self.approved_hoppers()
        own = self.hopper_bases(hoppers)

        if self.blogroll_only:
            log('Subscriptions')
            self.ensure_subscriptions(own, poll=False)  # backfill already starts each import
            log('Hopper feeds')
            routes = self.ensure_hopper_subscriptions(hoppers)
            self.log_routes(routes)
            log('Blogroll')
            added = self.ensure_blogroll(own)
            log(f'--blogroll-only: {len(added)} blyg(s) added to the blogroll; no filing, no digest.')
            return {'filed': [], 'digest': None, 'missing': [], 'blogroll_added': added, 'routes': routes}

        log('Hopper feeds')
        routes = self.ensure_hopper_subscriptions(hoppers)
        self.log_routes(routes)
        log('Wanted items')
        wanted = self.wanted_items(hoppers, routes)
        log(f'{len(wanted)} wanted item(s) on other blygs')

        log('Subscriptions')
        self.ensure_subscriptions({w['base'] for w in wanted} | own)

        log('Blogroll')
        added = self.ensure_blogroll(own)

        log(f'WM hopper /h/{self.slug}/')
        hopper = self.ensure_hopper()
        members = self.membership(hopper)
        log(f'  {len(members)} item(s) already filed')

        if self.digest:
            self.resume(hopper, members)

        index = self.imported_index({w['id'] for w in wanted})
        matched, missing = self.match(wanted, index)
        for w in missing:
            log(f"  not imported yet (next run): {item_ref(w['base'], w['kind'], w['id'])}")
        fresh = [r for r in matched if (r['subscriptionId'], r['remoteId']) not in members]
        # Oldest first, so a backlog reaches the digest in order.
        fresh.sort(key=lambda r: r.get('created') or r.get('observedAt') or '')
        cap = self.max_sources * self.max_scopes
        if self.digest and len(fresh) > cap:
            log(f'  {len(fresh)} new item(s); filing the oldest {cap}, the rest wait for the next run')
            fresh = fresh[:cap]

        log(f'Filing {len(fresh)} new item(s)')
        filed = self.file(hopper, fresh, members)

        result = {'filed': filed, 'digest': None, 'missing': missing, 'blogroll_added': added, 'routes': routes}
        if not filed:
            log('Nothing new; no digest.')
            return dict(result, filed=[])
        if not self.digest:
            log('--no-digest: skipping the digest.')
            return result

        hopper_url = f'{self.site}h/{(hopper or {}).get("slug") or self.slug}/'
        content = build_digest(filed, self.now, hopper_url, self.max_sources, self.hopper_name)
        result['digest'] = content
        log(f'Digest: {content.splitlines()[0]}')
        if not self.act(f'create the digest draft ({len(tk_scopes(content))} TK scope(s), {len(filed)} post(s))'):
            log('----- digest draft -----')
            log(content)
            log('------------------------')
            return result
        item = self.api.create_thread(content)
        log(f"    draft {item['id']}")
        self.generate_and_publish(item)
        result['item'] = item['id']
        return result

    def log_routes(self, routes):
        for c, r in routes.items():
            if r['path'] == 'feed':
                log(f"  {c}: hopper feed (subscription {r['sub'].get('id')}, {r['sub'].get('hopperFeedUrl')})")
            elif self.blogroll_only:
                log(f"  {c}: not read as a hopper feed — {r.get('why')}")
            else:
                log(f"  {c}: page scrape — {r.get('why')}")


def main(argv=None, transport=urllib_transport, fetch=fetch_text, sleep=time.sleep):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dry-run', action='store_true', help='read-only calls only; print the planned actions')
    p.add_argument('--no-digest', action='store_true', help='subscribe and file, but write no digest')
    p.add_argument('--blogroll-only', action='store_true',
                   help="only subscribe to approved hoppers' blygs (and hopper feeds, where offered) and put "
                        'the blygs in the blogroll; no page scraping, filing or digest')
    p.add_argument('--max-sources', type=int, default=MAX_SOURCES, help=f'sources per TK scope (default {MAX_SOURCES})')
    p.add_argument('--max-scopes', type=int, default=MAX_SCOPES, help=f'TK scopes per digest (default {MAX_SCOPES})')
    p.add_argument('--poll-wait', type=int, default=POLL_WAIT, help='seconds to wait after a forced poll')
    a = p.parse_args(argv)
    if a.max_sources < 1 or a.max_scopes < 1:
        p.error('--max-sources and --max-scopes must be at least 1')

    token = os.environ.get('BLYG_TOKEN')
    if not token:
        sys.exit('ERROR: BLYG_TOKEN is not set. Mint a Studio REST token (Studio → More → Client access) '
                 f'with {TOKEN_SCOPES} and store it as the BLYG_TOKEN secret.')
    api_base = os.environ.get('BLYG_API_BASE') or DEFAULT_API_BASE
    api = BlygApi(api_base, token, transport=transport, dry_run=a.dry_run, sleep=sleep)
    sync = Sync(
        api,
        fetch=fetch,
        sleep=sleep,
        site=os.environ.get('BLYG_SITE') or None,
        slug=os.environ.get('BLYG_HOPPER_SLUG') or DEFAULT_SLUG,
        hopper_name=os.environ.get('BLYG_HOPPER_NAME') or DEFAULT_HOPPER_NAME,
        hoppers_url=os.environ.get('WM_HOPPERS_URL') or DEFAULT_HOPPERS_URL,
        dry_run=a.dry_run,
        digest=not a.no_digest and not a.blogroll_only,
        blogroll_only=a.blogroll_only,
        max_sources=a.max_sources,
        max_scopes=a.max_scopes,
        poll_wait=a.poll_wait,
    )
    try:
        sync.run()
    except AuthError as e:
        print(f'::error::BLYG_TOKEN refused (HTTP {e.status}); mint a new Studio REST token', file=sys.stderr)
        sys.exit(str(e))
    except GenerationFailed as e:
        print(f'::error::digest generation failed: {e}', file=sys.stderr)
        sys.exit(f'ERROR: {e}')
    except BlygError as e:
        print(f'::error::{e}', file=sys.stderr)
        sys.exit(f'ERROR: {e}')


if __name__ == '__main__':
    main()
