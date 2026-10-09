#!/usr/bin/env python3
"""
Send an essay-length resource through wm-feeder and keep its L1 reading notes.

Resources are third-party writing, so their text never enters git. The ingest
job puts the extracted text straight into the feeder's R2 bucket; this script
starts a feeder run on it, waits, and copies only the run's `notes/*.md` into
raw-notes/commons/reading/<slug>/. The run's sidecars/ (verbatim quotes, plan)
and diagnostics stay in R2. A manifest at resource-runs/<slug>.json tells the
laptop-side loader where they are.

Usage:
  # Backfill or re-run one article: re-extract, upload, run, write notes,
  # mark the article "ingested", upload the manifest.
  python scripts/feed_resource.py content/articles/<slug>.json

  # CI (ingest job): upload already-extracted text.
  python scripts/feed_resource.py upload-text <slug> <file>

  # CI (feed job): text is already in R2; upload the manifest after commit.
  python scripts/feed_resource.py content/articles/<slug>.json \
      --skip-upload --defer-manifest <path>
  python scripts/feed_resource.py put-manifest <path>

Environment: FEEDER_URL, FEEDER_BUCKET, FEEDER_TOKEN, and for wrangler
CLOUDFLARE_API_TOKEN (R2 edit) + CLOUDFLARE_ACCOUNT_ID.

Stdlib only (trafilatura is imported lazily, for backfill re-extraction).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent
REPO = WEBSITE.parent
READING = REPO / 'raw-notes' / 'commons' / 'reading'

# Gating — which resources go to the feeder. ingest.py imports these.
FEED_FORMATS = {'essay', 'paper'}
MIN_CHARS = 1500
MAX_CHARS = 60000

LICENSE_CLASS = 'private'
POLL_INTERVAL = 10
POLL_ATTEMPTS = 90  # 15 minutes
USER_AGENT = 'worldmachines-ingest/1.0 (+https://worldmachines.org)'


def in_scope(type_, format_):
    return type_ == 'resource' and (format_ or '') in FEED_FORMATS


def gate(text, success):
    """None if the text should be fed, else the ingest_skipped reason."""
    if not success or not (text or '').strip():
        return 'extract_failed'
    n = len(text)
    if n < MIN_CHARS:
        return 'too_short'
    if n > MAX_CHARS:
        return 'too_long'
    return None


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def raw_key(slug):
    return f'raw/resources/{slug}.txt'


def manifest_key(slug):
    return f'resource-runs/{slug}.json'


def notes_dir(slug):
    return f'raw-notes/commons/reading/{slug}/'


# ---------------------------------------------------------------- R2 (wrangler)

def _env(name):
    val = os.environ.get(name)
    if not val:
        sys.exit(f'ERROR: {name} not set')
    return val


def _wrangler(*args):
    cmd = ['npx', '--yes', 'wrangler@4', 'r2', 'object', *args, '--remote']
    print('  $ ' + ' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=tempfile.gettempdir())  # cwd: avoid stray .env files


def r2_put(key, path, content_type='text/plain'):
    _wrangler('put', f"{_env('FEEDER_BUCKET')}/{key}", '--file', str(path),
              '--content-type', content_type)


def r2_get(key, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _wrangler('get', f"{_env('FEEDER_BUCKET')}/{key}", '--file', str(path))


def upload_text(slug, path):
    """Upload text (LF-normalized) to raw/resources/<slug>.txt. Returns the key."""
    text = normalize(Path(path).read_text(encoding='utf-8'))
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        tmp = f.name
    try:
        r2_put(raw_key(slug), tmp)
    finally:
        os.unlink(tmp)
    return raw_key(slug)


# ---------------------------------------------------------------- feeder API

def _api(method, path, body=None):
    url = _env('FEEDER_URL').rstrip('/') + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f"Bearer {_env('FEEDER_TOKEN')}",
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def run_body(article, key):
    return {
        'r2Key': key,
        'slug': article['slug'],
        'title': article.get('title') or article['slug'],
        'author': article.get('author') or '',
        'licenseClass': LICENSE_CLASS,
        'skipCanonize': True,
    }


def start_run(article, key):
    resp = _api('POST', '/runs', run_body(article, key))
    run_id = resp.get('id')
    if not run_id:
        sys.exit(f'ERROR: feeder did not return a run id: {resp}')
    print(f'  Started feeder run {run_id}')
    return run_id


def poll_run(run_id, attempts=POLL_ATTEMPTS, interval=POLL_INTERVAL, sleep=time.sleep):
    for i in range(1, attempts + 1):
        try:
            resp = _api('GET', f'/runs/{run_id}')
        except (urllib.error.URLError, TimeoutError) as err:
            print(f'  poll {i}/{attempts}: transient error {err!r}')
            sleep(interval)
            continue
        status = resp.get('status')
        print(f'  poll {i}/{attempts}: status={status}')
        if status == 'complete':
            return resp
        if status in ('errored', 'terminated'):
            sys.exit(f'ERROR: feeder run {run_id} ended {status}: {json.dumps(resp)[:2000]}')
        sleep(interval)
    sys.exit(f'ERROR: feeder run {run_id} did not complete in {attempts * interval}s')


def note_keys(result):
    """The artifact keys worth committing: notes/*.md only, never sidecars/diagnostics."""
    keys = (result.get('output') or {}).get('artifacts') or []
    out = []
    for k in keys:
        if not (k.startswith('notes/') and k.endswith('.md')):
            continue
        if '..' in Path(k).parts or k.startswith('/'):
            continue
        out.append(k)
    return out


def unquote_wikilinks(text):
    """Gemma sometimes wraps wiki-links in backticks (`[[x]]`), which makes
    them inline code that the lake won't resolve as links."""
    return re.sub(r'`(\[\[[^\]`]+\]\])`', r'\1', text)


def download_notes(run_id, result, slug):
    keys = note_keys(result)
    if not keys:
        sys.exit(f'ERROR: feeder run {run_id} produced no notes/*.md: {result.get("output")}')
    dest = READING / slug
    dest.mkdir(parents=True, exist_ok=True)
    for k in keys:
        path = dest / k[len('notes/'):]
        r2_get(f'runs/{run_id}/{k}', path)
        path.write_text(unquote_wikilinks(path.read_text(encoding='utf-8')), encoding='utf-8')
    print(f'  Wrote {len(keys)} note(s) to {dest.relative_to(REPO)}/')
    return keys


def build_manifest(article, run_id, completed_at=None):
    slug = article['slug']
    return {
        'slug': slug,
        'title': article.get('title') or slug,
        'url': article.get('url'),
        'handle': article.get('handle'),
        'kind': article.get('format'),
        'license_class': LICENSE_CLASS,
        'run_id': run_id,
        'raw_key': raw_key(slug),
        'scout_prefix': f'runs/{run_id}/sidecars/',
        'notes_dir': notes_dir(slug),
        'completed_at': completed_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def put_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    r2_put(manifest_key(manifest['slug']), path, content_type='application/json')
    print(f"  Uploaded manifest {manifest_key(manifest['slug'])}")


# ---------------------------------------------------------------- backfill

def reextract(article, force=False):
    """Re-fetch the text; refresh title/published_at. Returns LF text (never stored in git)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from article_fetch import fetch_and_extract
    title, pub, text, ok = fetch_and_extract(article['url'])
    if title:
        article['title'] = title
    if pub and not article.get('published_at'):
        article['published_at'] = pub
    reason = gate(text, ok)
    if reason and not (force and text):
        sys.exit(f'ERROR: {article["slug"]}: {reason} ({len(text or "")} chars); --force to override')
    return normalize(text)


def save_article(path, article):
    Path(path).write_text(json.dumps(article, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def feed(article_path, skip_upload=False, defer_manifest=None, force=False):
    article_path = Path(article_path)
    article = json.loads(article_path.read_text(encoding='utf-8'))
    slug = article['slug']
    if not in_scope(article.get('type'), article.get('format')) and not force:
        sys.exit(f'ERROR: {slug} is not an essay/paper resource; --force to override')
    if article.get('extracted_text'):
        sys.exit(f'ERROR: {slug} has extracted_text in git; resources must not')

    if skip_upload:
        key = raw_key(slug)
    else:
        text = reextract(article, force=force)
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(text)
            tmp = f.name
        try:
            key = upload_text(slug, tmp)
        finally:
            os.unlink(tmp)
        print(f'  Uploaded {len(text)} chars to {key}')

    run_id = start_run(article, key)
    result = poll_run(run_id)
    download_notes(run_id, result, slug)

    article['extracted_text'] = None
    article.pop('ingest_skipped', None)
    article['ingest_status'] = 'ingested'
    save_article(article_path, article)

    manifest = build_manifest(article, run_id)
    if defer_manifest:
        Path(defer_manifest).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print(f'  Manifest written to {defer_manifest} (upload after commit)')
    else:
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
            tmp = f.name
        try:
            put_manifest(tmp)
        finally:
            os.unlink(tmp)
    return manifest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == 'upload-text':
        if len(argv) != 3:
            sys.exit('usage: feed_resource.py upload-text <slug> <file>')
        print(f'  Uploaded to {upload_text(argv[1], argv[2])}')
        return
    if argv and argv[0] == 'put-manifest':
        if len(argv) != 2:
            sys.exit('usage: feed_resource.py put-manifest <file>')
        put_manifest(argv[1])
        return
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('article', help='content/articles/<slug>.json')
    p.add_argument('--skip-upload', action='store_true',
                   help='text is already at raw/resources/<slug>.txt; do not re-extract')
    p.add_argument('--defer-manifest', metavar='PATH',
                   help='write the manifest here instead of uploading it')
    p.add_argument('--force', action='store_true',
                   help='feed even if out of scope or outside the length cap')
    a = p.parse_args(argv)
    feed(a.article, skip_upload=a.skip_upload, defer_manifest=a.defer_manifest, force=a.force)


if __name__ == '__main__':
    main()
