#!/usr/bin/env python3
"""
Collect member hopper posts into the World Machines blyg and publish a digest.

Members propose their WM-related blyg hoppers at worldmachines.org/hoppers;
approved ones are listed by GET https://worldmachines.org/api/hoppers. A remote
hopper has no feed (it is an HTML page), so this script:

  1. reads each approved hopper's public page and picks out its items'
     permalinks ({blyg base}t/{id}/ or f/{id}/);
  2. makes the WM blyg subscribe to every blyg those items live on (the whole
     blyg; the hopper page decides which of its posts we keep);
  3. matches each wanted item to the WM blyg's imported copy
     (GET /reading/imported) — items not imported yet wait for the next run;
  4. files the matched items into the WM hopper (default slug `members`). This
     is curation only: they show on blyg.worldmachines.org/h/members/;
  5. writes a [TK] digest thread over the newly filed posts, has the Studio's
     model (Gemma on Workers AI) generate each scope, and publishes it.

Stateless: the WM hopper's membership is the watermark. A run that finds
nothing new files nothing and posts nothing. When generation fails (the shared
AI budget is 20 calls a day), the digest stays a draft and the next run finds
it by its title, files anything it names that is not filed yet, and retries the
missing scopes instead of starting a duplicate.

Usage (from website/):
  python scripts/blyg_sync.py --dry-run          # read-only; print the plan
  python scripts/blyg_sync.py                    # sync, file, digest
  python scripts/blyg_sync.py --no-digest        # sync and file only

Environment:
  BLYG_TOKEN        Studio REST token (Studio → More → Client access → REST API)
                    with scopes owner:read owner:manage owner:draft owner:publish.
                    Expires after at most 30 days.
  BLYG_API_BASE     default https://blyg.worldmachines.org/api
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


def log(msg=''):
    print(msg, flush=True)


# ---------------------------------------------------------------- errors

class BlygError(Exception):
    def __init__(self, status, method, path, body):
        self.status, self.method, self.path, self.body = status, method, path, body
        detail = body.get('error') if isinstance(body, dict) else body
        super().__init__(f'{method} {path} → HTTP {status}: {detail}')


class AuthError(BlygError):
    studio = 'https://blyg.worldmachines.org/studio'

    def __str__(self):
        detail = self.body.get('error') if isinstance(self.body, dict) else self.body
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

    The API base is configuration (BLYG_API_BASE) because blygger-studio #97
    moves it under the mount; when #98 lands (observed revisions on
    mutations), request() is the one place to add the header.
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

    def request(self, method, path, body=None, query=None, ok=(200, 201), retry_429=True):
        """JSON request. Returns (status, json). Raises AuthError / BlygError."""
        if method != 'GET' and self.dry_run:
            raise RuntimeError(f'dry run: refusing to send {method} {path}')
        url = self.base + path
        if query:
            url += '?' + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
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
                payload = {'error': raw[:300].decode(errors='replace')}
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

    # -- reads
    def subscriptions(self):
        return list(self._offset_paged('/subscriptions'))

    def hoppers(self):
        return list(self._offset_paged('/hoppers'))

    def hopper(self, hopper_id):
        return self.get(f'/hoppers/{q(hopper_id)}')

    def items(self):
        return list(self._offset_paged('/items'))

    def imported(self, limit=100):
        """Yield /reading/imported rows, newest observed first (cursor-paged)."""
        cursor = None
        for _ in range(1000):
            page = self.get('/reading/imported', limit=limit, cursor=cursor)
            yield from page.get('items') or []
            cursor = page.get('next')
            if not cursor:
                return

    def _offset_paged(self, path, limit=100):
        offset = 0
        while True:
            page = self.get(path, offset=offset, limit=limit)
            rows = page.get('items') or []
            yield from rows
            offset += len(rows)
            if not rows or offset >= (page.get('total') or 0):
                return

    # -- writes
    def subscribe(self, url):
        """(status, body). 201 created; 200 proposal needing owner confirmation; 409 already subscribed."""
        return self.request('POST', '/subscriptions', {'url': url, 'confirm': True, 'backfill': True},
                            ok=(200, 201, 409, 422))

    def poll(self):
        return self.request('POST', '/subscriptions/poll')[1]

    def create_hopper(self, name):
        return self.request('POST', '/hoppers', {'name': name})[1]

    def patch_hopper(self, hopper_id, **fields):
        return self.request('PATCH', f'/hoppers/{q(hopper_id)}', fields)[1]

    def file(self, hopper_id, sub_id, remote_id):
        return self.request('PUT', f'/hoppers/{q(hopper_id)}/items/{q(sub_id)}/{q(remote_id)}')[1]

    def create_thread(self, content_md):
        return self.request('POST', '/items', {'kind': 'thread', 'content_md': content_md})[1]

    def patch_item(self, item_id, content_md):
        return self.request('PATCH', f'/items/{q(item_id)}', {'content_md': content_md})[1]

    def generate(self, item_id, scope):
        # 429 here is the daily AI budget, not a rate limit: never retry it.
        return self.request('POST', f'/items/{q(item_id)}/generate', {'scope': scope},
                            ok=(200,), retry_429=False)[1]

    def publish(self, item_id):
        return self.request('POST', f'/items/{q(item_id)}/publish', {})[1]


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
                 hoppers_url=DEFAULT_HOPPERS_URL, dry_run=False, digest=True, max_sources=MAX_SOURCES,
                 max_scopes=MAX_SCOPES, poll_wait=POLL_WAIT, sleep=time.sleep, now=None):
        self.api = api
        self.fetch = fetch
        self.site = norm_base(site or site_from_api_base(api.base))
        self.slug = slug
        self.hopper_name = hopper_name
        self.hoppers_url = hoppers_url
        self.dry_run = dry_run
        self.digest = digest
        self.max_sources = max_sources
        self.max_scopes = max_scopes
        self.poll_wait = poll_wait
        self.sleep = sleep
        self.now = now or datetime.now(timezone.utc)
        self.plan = []  # what a dry run would have done
        self._imported = None

    def act(self, description):
        """True when the action should happen; in a dry run, record it instead."""
        if self.dry_run:
            self.plan.append(description)
            log(f'  [dry-run] would {description}')
            return False
        log(f'  {description}')
        return True

    # 1–2: wanted items from the member hoppers
    def wanted_items(self):
        log(f'Reading approved hoppers from {self.hoppers_url}')
        hoppers = parse_wm_hoppers(json.loads(self.fetch(self.hoppers_url)))
        log(f'  {len(hoppers)} approved hopper(s)')
        wanted, seen = [], set()
        for h in hoppers:
            try:
                page = self.fetch(h['canonical'])
            except Exception as e:  # one unreachable blyg must not stop the others
                log(f"  ! could not read {h['canonical']}: {e}")
                continue
            items = extract_items(page, h['canonical'])
            log(f"  {h['canonical']}: {len(items)} item(s)")
            for base, kind, item_id in items:
                if base == self.site:
                    continue  # already ours
                if (base, item_id) not in seen:
                    seen.add((base, item_id))
                    wanted.append({'base': base, 'kind': kind, 'id': item_id, 'hopper': h['canonical']})
        return wanted

    # 3: subscriptions
    def ensure_subscriptions(self, bases):
        have = {norm_base(s['origin']) for s in self.api.subscriptions()}
        new = 0
        for base in sorted(bases):
            if base in have:
                continue
            if not self.act(f'subscribe to {base}'):
                continue
            status, body = self.api.subscribe(base)
            if status == 201:
                log(f"    subscribed: {body.get('title')} ({body.get('id')})")
                new += 1
            elif status == 200:
                log(f'    the blyg proposed a subscription but did not create it; confirm it in Studio: {body}')
            elif status == 409:
                log(f"    already subscribed ({body.get('error')})")
            else:
                log(f"    ! could not subscribe ({status}): {body.get('error') if isinstance(body, dict) else body}")
        if new and self.act('force a poll of all subscriptions'):
            log(f"    polling {self.api.poll().get('polling')} subscription(s); waiting {self.poll_wait}s")
            self.sleep(self.poll_wait)
        return new

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
        matched, missing = [], []
        for w in wanted:
            rows = index.get(w['id']) or []
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
        detail = self.api.hopper(hopper['id'])
        return {(m['subscription_id'], m['remote_id']) for m in detail.get('memberships') or []}

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
        drafts = [i for i in self.api.items()
                  if i.get('status') == 'draft' and (i.get('content_md') or '').startswith(DIGEST_PREFIX)]
        return sorted(drafts, key=lambda i: i.get('created') or '')[0] if drafts else None

    def generate_and_publish(self, item):
        content = item['content_md']
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
                body = e.body if isinstance(e.body, dict) else {}
                bad = body.get('id')
                if e.status == 400 and 'unresolvable source' in str(body.get('error')) and bad and bad not in dropped:
                    log(f"    source {bad} no longer resolves ({body.get('reason')}); dropping it from the digest")
                    dropped.add(bad)
                    content = drop_source(content, bad)
                    self.api.patch_item(item_id, content)
                    continue
                if e.status == 429:
                    raise GenerationFailed(
                        f'the daily AI budget is spent (HTTP 429: {body.get("error")}). The digest {item_id} '
                        'stays a draft; the next run retries it.') from e
                if e.status == 502:
                    raise GenerationFailed(
                        f'the model provider failed (HTTP 502: {body.get("error")}); a provider error still counts '
                        f'against the AI budget (a config error does not). The digest {item_id} stays a draft; the next run retries it.') from e
                raise GenerationFailed(f'generation failed: {e}. The digest {item_id} stays a draft.') from e
            content = result['content_md']
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
        title = draft['content_md'].splitlines()[0]
        log(f"Resuming unfinished digest {draft['id']}: {title}")
        ids = referenced_ids(draft['content_md'])
        index = self.imported_index(ids)
        rows = [index[i][0] for i in ids if index.get(i)]
        if hopper:
            self.file(hopper, rows, members)
        self.generate_and_publish(draft)
        return True

    def run(self):
        log(f'World Machines blyg: {self.site} (API {self.api.base})' + (' — DRY RUN' if self.dry_run else ''))
        wanted = self.wanted_items()
        log(f'{len(wanted)} wanted item(s) on other blygs')

        log('Subscriptions')
        self.ensure_subscriptions({w['base'] for w in wanted})

        log(f'WM hopper /h/{self.slug}/')
        hopper = self.ensure_hopper()
        members = self.membership(hopper)
        log(f'  {len(members)} item(s) already filed')

        if self.digest:
            self.resume(hopper, members)

        index = self.imported_index({w['id'] for w in wanted})
        matched, missing = self.match(wanted, index)
        for w in missing:
            log(f"  not imported yet (next run): {w['base']}{w['kind']}/{w['id']}/")
        fresh = [r for r in matched if (r['subscriptionId'], r['remoteId']) not in members]
        # Oldest first, so a backlog reaches the digest in order.
        fresh.sort(key=lambda r: r.get('created') or r.get('observedAt') or '')
        cap = self.max_sources * self.max_scopes
        if self.digest and len(fresh) > cap:
            log(f'  {len(fresh)} new item(s); filing the oldest {cap}, the rest wait for the next run')
            fresh = fresh[:cap]

        log(f'Filing {len(fresh)} new item(s)')
        filed = self.file(hopper, fresh, members)

        if not filed:
            log('Nothing new; no digest.')
            return {'filed': [], 'digest': None, 'missing': missing}
        if not self.digest:
            log('--no-digest: skipping the digest.')
            return {'filed': filed, 'digest': None, 'missing': missing}

        hopper_url = f'{self.site}h/{(hopper or {}).get("slug") or self.slug}/'
        content = build_digest(filed, self.now, hopper_url, self.max_sources, self.hopper_name)
        log(f'Digest: {content.splitlines()[0]}')
        if not self.act(f'create the digest draft ({len(tk_scopes(content))} TK scope(s), {len(filed)} post(s))'):
            log('----- digest draft -----')
            log(content)
            log('------------------------')
            return {'filed': filed, 'digest': content, 'missing': missing}
        item = self.api.create_thread(content)
        log(f"    draft {item['id']}")
        self.generate_and_publish(item)
        return {'filed': filed, 'digest': content, 'missing': missing, 'item': item['id']}


def main(argv=None, transport=urllib_transport, fetch=fetch_text, sleep=time.sleep):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dry-run', action='store_true', help='read-only calls only; print the planned actions')
    p.add_argument('--no-digest', action='store_true', help='subscribe and file, but write no digest')
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
        digest=not a.no_digest,
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
