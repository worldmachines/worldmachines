#!/usr/bin/env python3
"""
Fetch an article's text for ingest.py / ingest_inbox.py.

The ingest bot runs on GitHub Actions, whose datacenter IPs many sites
(Substack; anything behind Cloudflare bot protection) challenge, so a plain
page fetch often comes back empty. Instead of disguising the bot, this uses
the routes sites offer machines, in order:

  1. Substack's public post API, for any URL shaped like a Substack post
     (including custom domains, which serve the same API).
  2. The article page itself, extracted with trafilatura.
  3. The site's RSS/Atom feed, when it carries the post's full text.

Each route fetches directly first. GitHub's runners sit on Azure IPs that
Substack and Cloudflare-protected blogs answer with a 403 challenge (whatever
the User-Agent), so when INGEST_RELAY_TOKEN is set a failed direct fetch is
retried through /api/ingest-relay, which makes the same request from
Cloudflare's network.

Every request identifies itself honestly as USER_AGENT, so a site owner can
allowlist (or block) the bot with one rule.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse

import trafilatura
from trafilatura.settings import use_config

USER_AGENT = 'worldmachines-ingest/1.0 (+https://worldmachines.org)'

# A feed entry shorter than this is treated as a summary, not the article.
MIN_FEED_TEXT = 1500

FEED_PATHS = ['/feed', '/index.xml', '/rss.xml', '/feed.xml', '/atom.xml', '/rss']

_config = use_config()
_config.set('DEFAULT', 'USER_AGENTS', USER_AGENT)


RELAY_URL = os.environ.get('INGEST_RELAY_URL', 'https://worldmachines.org/api/ingest-relay')
RELAY_TOKEN = os.environ.get('INGEST_RELAY_TOKEN', '')


def relay_get(query):
    """GET /api/ingest-relay?<query>. Returns the decoded body on a 200, else None."""
    if not RELAY_TOKEN:
        return None
    req = urllib.request.Request(
        f'{RELAY_URL}?{query}',
        headers={'Authorization': f'Bearer {RELAY_TOKEN}', 'User-Agent': USER_AGENT},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                charset = res.headers.get_content_charset() or 'utf-8'
                return res.read().decode(charset, errors='replace')
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt:
                return None
            time.sleep(5)
        except (urllib.error.URLError, TimeoutError):
            return None
    return None


def _get(url):
    """GET url as the ingest bot: directly, then via the relay. Body or None."""
    body = trafilatura.fetch_url(url, config=_config)
    if body is None:
        body = relay_get(f'url={quote(url, safe="")}')
        if body is not None:
            print(f"    (via relay: {url})")
    return body


def fetch_pasted(key):
    """Text a member pasted on /submit, stored in R2 by functions/api/submit.js."""
    return relay_get(f'pasted={quote(key, safe="")}')


def _html_to_text(fragment):
    return trafilatura.extract(
        f'<html><body><article>{fragment}</article></body></html>',
        include_comments=False, include_tables=False,
    )


# ── 1. Substack API ─────────────────────────────────────────────────

def substack_api_url(url):
    """The post-API URL for a Substack-shaped link, or None."""
    p = urlparse(url)
    host = p.netloc.lower()
    path = p.path.rstrip('/')

    m = re.fullmatch(r'/pub/([\w-]+)/p/([\w-]+)', path)
    if host == 'open.substack.com' and m:
        return f'https://{m.group(1)}.substack.com/api/v1/posts/{m.group(2)}'

    m = re.fullmatch(r'/inbox/post/(\d+)', path)
    if host in ('substack.com', 'www.substack.com') and m:
        return f'https://substack.com/api/v1/posts/by-id/{m.group(1)}'

    # <pub>.substack.com/p/<slug> or a custom domain with the same shape.
    # On a non-Substack site this just 404s and we move on.
    m = re.fullmatch(r'/p/([\w-]+)', path)
    if m:
        return f'{p.scheme or "https"}://{p.netloc}/api/v1/posts/{m.group(1)}'
    return None


def fetch_substack(url):
    api = substack_api_url(url)
    if not api:
        return None
    raw = _get(api)
    if not raw:
        return None
    try:
        post = json.loads(raw)
    except ValueError:
        return None
    post = post.get('post', post) if isinstance(post, dict) else None
    if not post or not post.get('body_html'):
        return None
    text = _html_to_text(post['body_html'])
    if not text:
        return None
    title = (post.get('title') or '').strip() or None
    date = (post.get('post_date') or '')[:10] or None
    return title, date, text


# ── 2. The page itself ──────────────────────────────────────────────

def fetch_page(url):
    downloaded = _get(url)
    if downloaded is None:
        return None
    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    title = ((metadata.title if metadata else None) or '').strip() or None
    date = ((metadata.date if metadata else None) or '').strip() or None
    return title, date, text


# ── 3. RSS / Atom feed ──────────────────────────────────────────────

def _norm(url):
    p = urlparse(url)
    host = p.netloc.lower().removeprefix('www.')
    return f'{host}{p.path.rstrip("/")}'


def _iso_date(raw):
    """RSS (RFC 822) or Atom (ISO 8601) date → YYYY-MM-DD, like published_at elsewhere."""
    if not raw:
        return None
    if re.match(r'\d{4}-\d{2}-\d{2}', raw):
        return raw[:10]
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return None


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _feed_entries(xml):
    """Yield (link, title, date, body_html) for each RSS item / Atom entry."""
    root = ET.fromstring(xml)
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ('item', 'entry'):
            continue
        link = title = date = None
        bodies = []
        for child in el:
            name = _local(child.tag)
            if name == 'link':
                link = link or (child.get('href') or (child.text or '')).strip()
            elif name == 'title':
                title = (child.text or '').strip() or None
            elif name in ('pubDate', 'published', 'updated', 'date'):
                date = date or (child.text or '').strip() or None
            elif name in ('encoded', 'content', 'description', 'summary'):
                bodies.append(child.text or '')
        yield link, title, date, max(bodies, key=len, default='')


def fetch_feed(url):
    p = urlparse(url)
    origin = f'{p.scheme or "https"}://{p.netloc}'
    want = _norm(url)
    for path in FEED_PATHS:
        xml = _get(urljoin(origin, path))
        if not xml or '<' not in xml[:200]:
            continue
        try:
            entries = list(_feed_entries(xml.encode('utf-8')))
        except ET.ParseError:
            continue
        for link, title, date, body in entries:
            if not link or _norm(link) != want:
                continue
            text = _html_to_text(body)  # ElementTree has already unescaped it
            if text and len(text) >= MIN_FEED_TEXT:
                return title, _iso_date(date), text
            return None  # found the post, but the feed only has a summary
    return None


# ── Entry point ─────────────────────────────────────────────────────

def fetch_and_extract(url):
    """(title, published_at, text, success) — same contract as before."""
    title = date = None
    for method, fetch in (('substack-api', fetch_substack), ('page', fetch_page), ('feed', fetch_feed)):
        try:
            got = fetch(url)
        except Exception as err:  # one route failing must not sink the others
            print(f"  {method}: error {err!r}")
            continue
        if not got:
            continue
        t, d, text = got
        title, date = title or t, date or d
        if text:
            print(f"  Fetched via: {method}")
            return title, date, text, True
    return title, date, None, False


if __name__ == '__main__':
    import sys
    for u in sys.argv[1:]:
        print(u)
        t, d, text, ok = fetch_and_extract(u)
        print(f"  -> ok={ok} title={t!r} date={d!r} chars={len(text or '')}")
