"""Gating tests for essay/paper resources → wm-feeder.

Run from website/:  python -m unittest discover -s tests
Network is never touched: fetch_and_extract is mocked, and trafilatura is
stubbed if it is not installed.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS))

try:
    import trafilatura  # noqa: F401
except ImportError:  # article_fetch imports it at module level
    fake = types.ModuleType('trafilatura')
    fake_settings = types.ModuleType('trafilatura.settings')

    class _Cfg:
        def set(self, *a):
            pass

    fake_settings.use_config = lambda: _Cfg()
    fake.settings = fake_settings
    sys.modules['trafilatura'] = fake
    sys.modules['trafilatura.settings'] = fake_settings

import feed_resource  # noqa: E402
import ingest  # noqa: E402


def payload(type_='resource', format_='essay', **kw):
    p = {'url': 'https://example.com/p/some-essay', 'handle': 'vgr', 'type': type_,
         'format': format_, 'submitted_at': '2026-10-08T00:00:00Z'}
    p.update(kw)
    return p


class IngestRun:
    """Run ingest.main() in a temp dir with a mocked fetch; return (article, outputs, text_files)."""

    def __init__(self, test, fetched):
        self.test, self.fetched = test, fetched

    def __call__(self, p):
        with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as textdir:
            out_file = os.path.join(work, 'gh_output')
            env = {'SUBMISSION_PAYLOAD': json.dumps(p), 'GITHUB_OUTPUT': out_file,
                   'FEED_TEXT_DIR': textdir}
            cwd = os.getcwd()
            os.chdir(work)
            try:
                with mock.patch.dict(os.environ, env), \
                        mock.patch.object(ingest, 'fetch_and_extract', return_value=self.fetched) as fx, \
                        mock.patch.object(ingest, 'fetch_pasted', return_value='pasted body ' * 300):
                    ingest.main()
                self.calls = fx.call_count
                files = os.listdir('content/articles')
                self.test.assertEqual(len(files), 1)
                article = json.loads(Path('content/articles', files[0]).read_text())
                outputs = dict(line.split('=', 1) for line in Path(out_file).read_text().splitlines())
                texts = {f: Path(textdir, f).read_text() for f in os.listdir(textdir)}
            finally:
                os.chdir(cwd)
        return article, outputs, texts


def body(n):
    return ('x' * 99 + '\n') * (n // 100) + 'y' * (n % 100)


class GateTests(unittest.TestCase):
    def test_boundaries(self):
        g = feed_resource.gate
        self.assertEqual(g(body(1499), True), 'too_short')
        self.assertIsNone(g(body(1500), True))
        self.assertIsNone(g(body(60000), True))
        self.assertEqual(g(body(60001), True), 'too_long')

    def test_extract_failed(self):
        g = feed_resource.gate
        self.assertEqual(g(None, False), 'extract_failed')
        self.assertEqual(g('', True), 'extract_failed')
        self.assertEqual(g('   \n', True), 'extract_failed')
        self.assertEqual(g(body(5000), False), 'extract_failed')

    def test_scope(self):
        s = feed_resource.in_scope
        self.assertTrue(s('resource', 'essay'))
        self.assertTrue(s('resource', 'paper'))
        for fmt in ('book', 'short story', 'supplement', None, ''):
            self.assertFalse(s('resource', fmt), fmt)
        self.assertFalse(s('contribution', 'essay'))


class IngestResourceTests(unittest.TestCase):
    def test_essay_in_cap_is_queued_without_text_in_json(self):
        text = body(5000)
        article, out, texts = IngestRun(self, ('Real Title', '2025-03-01', text, True))(payload())
        self.assertIsNone(article['extracted_text'])
        self.assertEqual(article['title'], 'Real Title')
        self.assertEqual(article['published_at'], '2025-03-01')
        self.assertEqual(article['ingest_status'], 'queued')
        self.assertNotIn('ingest_skipped', article)
        self.assertEqual(out['feed_queued'], 'true')
        self.assertEqual(out['slug'], article['slug'])
        self.assertEqual(out['kind'], 'essay')
        self.assertEqual(out['title'], 'Real Title')
        self.assertEqual(texts, {f"{article['slug']}.txt": text})

    def test_paper_crlf_normalized(self):
        text = 'line one\r\n' * 300
        article, out, texts = IngestRun(self, ('P', None, text, True))(payload(format_='paper'))
        self.assertEqual(out['kind'], 'paper')
        self.assertEqual(list(texts.values()), [text.replace('\r\n', '\n')])

    def _skipped(self, fetched, reason):
        article, out, texts = IngestRun(self, fetched)(payload())
        self.assertIsNone(article['extracted_text'])
        self.assertEqual(article['ingest_skipped'], reason)
        self.assertNotIn('ingest_status', article)
        self.assertEqual(out['feed_queued'], 'false')
        self.assertEqual(texts, {})
        return article

    def test_too_short(self):
        a = self._skipped(('Short', '2025-01-01', body(1499), True), 'too_short')
        self.assertEqual(a['title'], 'Short')  # real title still recorded

    def test_too_long(self):
        self._skipped(('Long', None, body(60001), True), 'too_long')

    def test_extract_failed_uses_url_title(self):
        a = self._skipped((None, None, None, False), 'extract_failed')
        self.assertEqual(a['title'], 'Some Essay')

    def test_book_resource_unchanged_link_only(self):
        run = IngestRun(self, ('X', None, body(5000), True))
        article, out, texts = run(payload(format_='book'))
        self.assertEqual(run.calls, 0)
        self.assertIsNone(article['extracted_text'])
        self.assertFalse(article['extraction_success'])
        self.assertEqual(article['title'], 'Some Essay')
        self.assertNotIn('ingest_status', article)
        self.assertNotIn('ingest_skipped', article)
        self.assertEqual(out['feed_queued'], 'false')
        self.assertEqual(texts, {})

    def test_pasted_text_ignored_for_resources(self):
        article, out, _ = IngestRun(self, (None, None, None, False))(payload(pasted_key='_ingest/pasted/x.txt'))
        self.assertIsNone(article['extracted_text'])
        self.assertEqual(article['ingest_skipped'], 'extract_failed')


class IngestContributionTests(unittest.TestCase):
    def test_contribution_keeps_text_and_never_queues(self):
        text = body(100000)  # over the resource cap — irrelevant for contributions
        article, out, texts = IngestRun(self, ('Mine', '2026-01-01', text, True))(payload(type_='contribution'))
        self.assertEqual(article['extracted_text'], text)
        self.assertTrue(article['extraction_success'])
        self.assertNotIn('ingest_status', article)
        self.assertNotIn('ingest_skipped', article)
        self.assertEqual(out['feed_queued'], 'false')
        self.assertEqual(texts, {})

    def test_contribution_pasted_text_wins(self):
        article, _, _ = IngestRun(self, ('T', None, 'teaser', True))(
            payload(type_='contribution', pasted_key='_ingest/pasted/x.txt'))
        self.assertTrue(article['extracted_text'].startswith('pasted body'))


class FeederHelperTests(unittest.TestCase):
    def test_note_keys_only_notes_md(self):
        result = {'output': {'artifacts': [
            'notes/a.md', 'notes/sub/b.md', 'notes/c.json', 'sidecars/chunks-01.yaml',
            'sidecars/plan.json', 'diagnostics.json', 'notes/../escape.md']}}
        self.assertEqual(feed_resource.note_keys(result), ['notes/a.md', 'notes/sub/b.md'])

    def test_manifest_contract(self):
        art = {'slug': 's-1', 'title': 'T', 'url': 'https://u', 'handle': 'h', 'format': 'paper'}
        m = feed_resource.build_manifest(art, 'run9', completed_at='2026-10-08T00:00:00Z')
        self.assertEqual(m, {
            'slug': 's-1', 'title': 'T', 'url': 'https://u', 'handle': 'h', 'kind': 'paper',
            'license_class': 'private', 'run_id': 'run9', 'raw_key': 'raw/resources/s-1.txt',
            'scout_prefix': 'runs/run9/sidecars/', 'notes_dir': 'raw-notes/commons/reading/s-1/',
            'completed_at': '2026-10-08T00:00:00Z'})
        self.assertEqual(feed_resource.manifest_key('s-1'), 'resource-runs/s-1.json')

    def test_run_body(self):
        b = feed_resource.run_body({'slug': 's', 'title': 'T'}, 'raw/resources/s.txt')
        self.assertEqual(b, {'r2Key': 'raw/resources/s.txt', 'slug': 's', 'title': 'T', 'author': '',
                             'licenseClass': 'private', 'skipCanonize': True})

    def test_poll_fails_loudly_on_error(self):
        with mock.patch.object(feed_resource, '_api', return_value={'status': 'errored'}):
            with self.assertRaises(SystemExit):
                feed_resource.poll_run('r', attempts=2, sleep=lambda s: None)

    def test_poll_returns_on_complete(self):
        seq = iter([{'status': 'running'}, {'status': 'complete', 'output': {}}])
        with mock.patch.object(feed_resource, '_api', side_effect=lambda *a, **k: next(seq)):
            self.assertEqual(feed_resource.poll_run('r', attempts=3, sleep=lambda s: None)['status'], 'complete')


if __name__ == '__main__':
    unittest.main()
