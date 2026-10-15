"""Check the archive and custom layer without loading the upstream plugin."""
from pathlib import Path
from unittest import mock
import hashlib
import io
import json
import os
import re
import runpy
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def test_source_snapshots_match_recorded_hashes(self):
        manifest = json.loads((ROOT / 'provenance.json').read_text())
        self.assertEqual(len(manifest['files']), 3)
        for item in manifest['files']:
            self.assertEqual(hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest(),
                             item['sha256'], item['path'])

    def test_configs_have_no_credentials_or_full_settings(self):
        display = json.loads((ROOT / 'config/hud-config.example.json').read_text())
        self.assertEqual(set(display), {'display', 'gitStatus'})
        self.assertNotIn('promptCacheTtlSeconds', display['display'])
        settings = json.loads((ROOT / 'config/statusline.example.json').read_text())
        self.assertEqual(set(settings), {'statusLine'})
        self.assertEqual(settings['statusLine']['type'], 'command')
        for p in (ROOT / 'config').glob('*.json'):
            self.assertIsInstance(json.loads(p.read_text()), dict)
            self.assertNotRegex(p.read_text().lower(), r'api[_-]?key|auth[_-]?token|password|secret')

    def test_document_relative_links_exist(self):
        documents = list(ROOT.glob('*.md')) + list((ROOT / 'docs').glob('*.md'))
        self.assertGreaterEqual(len(documents), 7)
        for document in documents:
            for link in re.findall(r'\]\(([^)]+)\)', document.read_text()):
                if '://' in link or link.startswith('#'):
                    continue
                target = link.split('#', 1)[0]
                self.assertTrue((document.parent / target).exists(), (document.name, target))

    def test_license_and_upstream_identity_are_recorded(self):
        manifest = json.loads((ROOT / 'provenance.json').read_text())
        self.assertEqual(manifest['upstream']['version'], '0.11.2')
        license_text = (ROOT / manifest['upstream']['license_file']).read_text()
        self.assertIn('Copyright (c) 2026 Jarrod Watts', license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)


class DependencySafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hud-dependency-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plugin = self.root / 'plugin'
        self.plugin.mkdir()
        self.module = runpy.run_path(str(ROOT / 'tests/test_hud.py'), run_name='dependency_helpers_only')

    def test_dist_link_is_rejected_before_reading_its_target(self):
        dist = self.plugin / 'dist'
        dist.mkdir()
        sentinel = self.root / 'outside-sentinel.txt'
        sentinel.write_text('synthetic sentinel, not user data')
        (dist / 'linked.js').symlink_to(sentinel)
        reads = []
        original = Path.read_bytes
        def observe(path):
            if path.resolve() == sentinel.resolve():
                reads.append(str(path))
            return original(path)
        rejected = False
        with mock.patch.object(Path, 'read_bytes', observe):
            try:
                self.module['tree_digest'](dist)
            except AssertionError:
                rejected = True
        self.assertEqual(reads, [], 'Dependency validation read a symlink target before rejection.')
        self.assertTrue(rejected, 'Dependency dist symlinks must be rejected.')

    def test_package_link_is_rejected_before_reading_its_target(self):
        sentinel = self.root / 'outside-package.json'
        sentinel.write_text(json.dumps({'version': '0.11.2'}))
        (self.plugin / 'package.json').symlink_to(sentinel)
        tests = self.module['HudTests']
        tests.setUpClass.__func__.__globals__['PLUGIN_ROOT'] = self.plugin
        reads = []
        original_text, original_bytes = Path.read_text, Path.read_bytes
        def observe_text(path, *args, **kwargs):
            if path.resolve() == sentinel.resolve():
                reads.append(str(path))
            return original_text(path, *args, **kwargs)
        def observe_bytes(path):
            if path.resolve() == sentinel.resolve():
                reads.append(str(path))
            return original_bytes(path)
        with mock.patch.object(Path, 'read_text', observe_text), \
                mock.patch.object(Path, 'read_bytes', observe_bytes):
            with self.assertRaises(AssertionError):
                tests.setUpClass()
        self.assertEqual(reads, [], 'Package validation read a symlink target before rejection.')

    def test_dist_root_link_is_rejected(self):
        outside = self.root / 'outside-dist'
        outside.mkdir()
        (outside / 'index.js').write_text('// Synthetic marker, never executed.\n')
        (self.plugin / 'dist').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AssertionError):
            self.module['tree_digest'](self.plugin / 'dist')


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hud-adapter-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / '.claude'
        self.cache = self.config / 'plugins/cache/claude-hud/claude-hud'
        for version in ['0.11.1', '0.11.2', '99.0.0-beta']:
            path = self.cache / version / 'dist/index.js'
            path.parent.mkdir(parents=True)
            path.write_text('// Test double marker; never executed.\n')
        self.env = {'HOME': str(self.root), 'CLAUDE_CONFIG_DIR': str(self.config),
                    'ANTHROPIC_BASE_URL': 'http://127.0.0.1:15721',
                    'ANTHROPIC_DEFAULT_OPUS_MODEL_NAME': 'example-model-label',
                    'CLAUDE_CODE_MAX_CONTEXT_TOKENS': '500000'}
        self.data = json.loads((ROOT / 'config/input.example.json').read_text())
        self.data['rate_limits'] = {'five_hour': {'used_percentage': 75}}
        self.data['prompt_cache'] = {'warm': True}
        self.module = runpy.run_path(str(ROOT / 'src/statusline-hud.py'), run_name='archived_hud')
        self.calls = []

    def execute(self, raw=None, timeout=False):
        def fake_run(command, **kwargs):
            self.calls.append((command, json.loads(kwargs['input'])))
            if command[0] == '/opt/homebrew/bin/node':
                if timeout:
                    raise subprocess.TimeoutExpired(command, 3)
                return subprocess.CompletedProcess(command, 0, 'Cost $12.34\n', '')
            return subprocess.CompletedProcess(command, 0, 'CACHE-TEST-DOUBLE\n', '')
        output = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch('sys.stdin', io.StringIO(json.dumps(self.data) if raw is None else raw)), \
                mock.patch('sys.stdout', output), mock.patch('subprocess.run', side_effect=fake_run):
            self.module['main']()
        return output.getvalue()

    def test_proxy_transform_and_highest_numeric_version(self):
        output = self.execute()
        command, payload = self.calls[0]
        self.assertEqual(command[1], str(self.cache / '0.11.2/dist/index.js'))
        self.assertEqual(payload['context_window']['context_window_size'], 500000)
        self.assertEqual(payload['context_window']['used_percentage'], 50)
        self.assertIn('请求 claude-opus-5', payload['model']['display_name'])
        self.assertIn('配置名 example-model-label', payload['model']['display_name'])
        self.assertNotIn('rate_limits', payload)
        self.assertNotIn('prompt_cache', payload)
        self.assertEqual(output, 'Cost 实付未知\nCACHE-TEST-DOUBLE\n')

    def test_native_payload_is_preserved(self):
        self.env['ANTHROPIC_BASE_URL'] = 'https://api.anthropic.com'
        self.assertIn('$12.34', self.execute())
        self.assertEqual(self.calls[0][1], self.data)

    def test_missing_usage_clears_stale_percentage(self):
        self.data['context_window'].pop('current_usage')
        self.execute()
        payload = self.calls[0][1]
        self.assertIsNone(payload['context_window']['used_percentage'])
        self.assertIsNone(payload['context_window']['current_usage'])
        self.assertIn('usage待报告', payload['model']['display_name'])

    def test_timeout_still_runs_cache_double(self):
        self.assertEqual(self.execute(timeout=True), 'CACHE-TEST-DOUBLE\n')
        self.assertEqual(len(self.calls), 2)

    def test_invalid_and_oversized_inputs_launch_no_child(self):
        for raw in ['{invalid', '[]', ' ' * (256 * 1024 + 1)]:
            self.calls.clear()
            self.assertEqual(self.execute(raw=raw), '')
            self.assertEqual(self.calls, [])


class CacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hud-cache-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.transcript = self.root / 'synthetic.jsonl'
        self.module = runpy.run_path(str(ROOT / 'src/cache-ratio-line.py'), run_name='archived_cache')

    @staticmethod
    def usage(mid, **fields):
        return json.dumps({'type': 'assistant', 'message': {'id': mid, 'usage': fields}}) + '\n'

    def execute(self):
        output = io.StringIO()
        with mock.patch('sys.stdin', io.StringIO(json.dumps({'transcript_path': str(self.transcript)}))), \
                mock.patch('sys.stdout', output), mock.patch('tempfile.gettempdir', return_value=str(self.root)):
            self.module['main']()
        return output.getvalue()

    def test_repeated_message_usage_is_not_added_twice(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=0)
                                  + self.usage('m1', input_tokens=900, cache_read_input_tokens=100)
                                  + self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.assertIn('10.0%', self.execute())

    def test_missing_uncached_count_is_unknown(self):
        self.transcript.write_text(self.usage('m1', cache_read_input_tokens=100))
        self.assertIn('未知', self.execute())

    def test_public_cache_is_replaced_with_private_recomputed_data(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute()
        cache = next(self.root.glob('cchud-cache-v2-*.json'))
        forged = json.loads(cache.read_text())
        forged['totals'] = [100, 0, 900]
        cache.write_text(json.dumps(forged))
        cache.chmod(0o666)
        self.assertIn('10.0%', self.execute())
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_symlink_target_is_not_modified(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute()
        cache = next(self.root.glob('cchud-cache-v2-*.json'))
        victim = self.root / 'victim.json'
        victim.write_text('private-test-sentinel')
        cache.unlink()
        cache.symlink_to(victim)
        self.assertIn('10.0%', self.execute())
        self.assertEqual(victim.read_text(), 'private-test-sentinel')
        self.assertFalse(cache.is_symlink())

    def test_same_size_rewrite_recomputes_counts(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute()
        self.transcript.write_text(self.usage('m1', input_tokens=100, cache_read_input_tokens=900))
        self.assertIn('90.0%', self.execute())


if __name__ == '__main__':
    unittest.main(verbosity=2)
