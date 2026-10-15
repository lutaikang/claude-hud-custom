"""Run synthetic-input integration tests against a pinned installed HUD."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
PLUGIN_ROOT = None
REAL_HOME = Path.home().resolve()
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def tree_digest(root):
    if root.is_symlink() or not root.is_dir():
        raise AssertionError('Dependency dist must be a real directory, not a symbolic link.')
    boundary = root.resolve()
    entries = sorted(root.rglob('*'))
    for path in entries:
        if path.is_symlink() or not path.resolve().is_relative_to(boundary):
            raise AssertionError('Dependency dist contains a symbolic link or escaped path.')
    rows = [p.relative_to(root).as_posix() + '\0' + hashlib.sha256(p.read_bytes()).hexdigest() + '\n'
            for p in entries if p.is_file()]
    return hashlib.sha256(''.join(rows).encode()).hexdigest()


class HudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PLUGIN_ROOT is None:
            raise unittest.SkipTest('Run this file with --plugin-root for the real-plugin suite.')
        manifest = json.loads((ROOT / 'provenance.json').read_text())['upstream']
        package = PLUGIN_ROOT / 'package.json'
        if package.is_symlink() or not package.resolve().is_relative_to(PLUGIN_ROOT.resolve()):
            raise AssertionError('Dependency package.json must not be a symbolic link or escaped path.')
        if not package.is_file():
            raise AssertionError('The supplied plugin root has no package.json.')
        if json.loads(package.read_text()).get('version') != manifest['version']:
            raise AssertionError('The plugin version differs from provenance.json.')
        if hashlib.sha256(package.read_bytes()).hexdigest() != manifest['package_sha256']:
            raise AssertionError('The plugin package differs from the captured dependency.')
        if tree_digest(PLUGIN_ROOT / 'dist') != manifest['dist_tree_sha256']:
            raise AssertionError('The plugin dist tree differs from the captured dependency.')

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='claude-hud-custom-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        config = self.root / 'home/.claude'
        config.mkdir(parents=True)
        for name in ['statusline-hud-plus-cache.sh', 'cache-ratio-line.py', 'statusline-hud.py']:
            shutil.copy2(SOURCE / name, config / name)
        cache = config / 'plugins/cache/claude-hud/claude-hud'
        cache.mkdir(parents=True)
        (cache / '0.11.2').symlink_to(PLUGIN_ROOT, target_is_directory=True)
        settings = config / 'plugins/claude-hud'
        settings.mkdir()
        (settings / 'config.json').write_text(json.dumps({
            'language': 'en',
            'display': {'showModel': True, 'contextValue': 'both', 'showContextBar': True,
                        'showCost': True, 'showUsage': True, 'showPromptCache': True,
                        'showConfigCounts': False, 'showTools': False, 'showAgents': False,
                        'showTodos': False, 'showDuration': False, 'showSpeed': False},
            'gitStatus': {'enabled': False},
        }))
        self.transcript = self.root / 'transcript.jsonl'
        self.transcript.write_text('')
        self.profile = self.root / 'sandbox.sb'
        quote = lambda value: json.dumps(str(value))
        ancestors = [p for p in PLUGIN_ROOT.parents if p == REAL_HOME or REAL_HOME in p.parents]
        metadata = ' '.join('(literal ' + quote(p) + ')' for p in ancestors)
        self.profile.write_text('\n'.join([
            '(version 1)', '(allow default)',
            '(deny file-read* (subpath ' + quote(REAL_HOME) + '))',
            '(allow file-read* (subpath ' + quote(PLUGIN_ROOT) + ') (subpath ' + quote(self.root) + '))',
            '(allow file-read-metadata ' + metadata + ')' if metadata else '',
            '(deny file-write*)',
            '(allow file-write* (subpath ' + quote(self.root) + ') (literal "/dev/null"))',
            '(deny mach-lookup (global-name "com.apple.securityd"))',
            '(deny network*)',
        ]))
        self.env = {
            'HOME': str(config.parent), 'CLAUDE_CONFIG_DIR': str(config), 'TMPDIR': str(self.root),
            'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'ANTHROPIC_BASE_URL': 'http://127.0.0.1:15721',
            'ANTHROPIC_DEFAULT_OPUS_MODEL_NAME': 'example-model-label',
            'CLAUDE_CODE_MAX_CONTEXT_TOKENS': '500000',
            'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_TELEMETRY': '1',
        }
        self.input = {
            'version': '2.1.296', 'transcript_path': str(self.transcript),
            'model': {'id': 'claude-opus-5', 'display_name': 'Opus 5'},
            'context_window': {'context_window_size': 1000000, 'used_percentage': 25,
                               'current_usage': {'input_tokens': 20000,
                                                 'cache_creation_input_tokens': 30000,
                                                 'cache_read_input_tokens': 200000}},
            'cost': {'total_cost_usd': 12.34},
            'prompt_cache': {'caching_observed': True, 'warm': True, 'ttl': '5m',
                             'expires_at': time.time() + 300},
            'rate_limits': {'five_hour': {'used_percentage': 75, 'resets_at': time.time() + 3600}},
        }

    def execute(self, kind='hud', raw=None, strip_ansi=True):
        config = Path(self.env['CLAUDE_CONFIG_DIR'])
        target = (['/bin/bash', str(config / 'statusline-hud-plus-cache.sh')] if kind == 'hud'
                  else ['/usr/bin/python3', '-I', str(config / 'cache-ratio-line.py')])
        result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(self.profile), *target],
                                input=json.dumps(self.input) if raw is None else raw,
                                text=True, capture_output=True, env=self.env,
                                cwd=self.root, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr[:700])
        return ANSI.sub('', result.stdout) if strip_ansi else result.stdout

    @staticmethod
    def usage(mid, **fields):
        return json.dumps({'type': 'assistant', 'message': {'id': mid, 'role': 'assistant', 'usage': fields}}) + '\n'

    def test_context_uses_policy_capacity_not_native_alias_capacity(self):
        output = self.execute()
        self.assertIn('50%', output)
        self.assertIn('500k', output)

    def test_proxy_model_is_labeled_as_request_not_served_model(self):
        output = self.execute()
        self.assertIn('请求', output)
        self.assertIn('配置名 example-model-label', output)

    def test_proxy_request_identity_does_not_use_cosmetic_display_name(self):
        self.input['model']['display_name'] = 'example-model-label'
        output = self.execute()
        self.assertIn('请求 claude-opus-5', output)
        self.assertIn('配置名 example-model-label', output)

    def test_proxy_does_not_present_claude_price_as_oauth_bill(self):
        output = self.execute()
        self.assertNotIn('$12.34', output)
        self.assertIn('实付未知', output)

    def test_proxy_does_not_claim_anthropic_ttl_or_quota(self):
        output = self.execute()
        self.assertNotIn('75%', output)
        self.assertNotIn('⏱', output)

    def test_native_provider_keeps_native_metrics(self):
        self.env['ANTHROPIC_BASE_URL'] = 'https://api.anthropic.com'
        output = self.execute()
        self.assertIn('25%', output)
        self.assertIn('$12.34', output)
        self.assertNotIn('配置名', output)

    def test_adapter_does_not_add_policy_rows(self):
        output = self.execute()
        for label in ['策略容量', '压缩配置', '压缩目标']:
            self.assertNotIn(label, output)
        self.assertEqual(len(output.rstrip().splitlines()), 2)

    def test_zero_usage_still_uses_policy_capacity(self):
        self.input['context_window']['current_usage'] = {
            'input_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
        output = self.execute()
        self.assertIn('500k', output)
        self.assertNotIn('1.0M', output)
        self.assertNotIn('25%', output)

    def test_missing_usage_is_labeled_and_does_not_keep_old_percentage(self):
        self.input['context_window'].pop('current_usage')
        output = self.execute()
        self.assertIn('500k', output)
        self.assertIn('usage待报告', output)
        self.assertNotIn('25%', output)
        self.assertNotIn('1.0M', output)

    def test_hud_palette_is_not_extended(self):
        proxied = self.execute(strip_ansi=False)
        self.env['ANTHROPIC_BASE_URL'] = 'https://api.anthropic.com'
        native = self.execute(strip_ansi=False)
        self.assertTrue(set(ANSI.findall(proxied)).issubset(set(ANSI.findall(native))))
        self.assertTrue(ANSI.findall(proxied))

    def test_cache_symlink_is_not_followed(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute('cache')
        cache = next(self.root.glob('cchud-cache-v2-*.json'))
        forged = json.loads(cache.read_text())
        forged['totals'] = [100, 0, 900]
        victim = self.root / 'not-a-cache.json'
        content = json.dumps(forged)
        victim.write_text(content)
        cache.unlink()
        cache.symlink_to(victim)
        self.assertIn('10.0%', self.execute('cache'))
        self.assertEqual(victim.read_text(), content)
        self.assertFalse(cache.is_symlink())

    def test_public_cache_is_recomputed_and_replaced_privately(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute('cache')
        cache = next(self.root.glob('cchud-cache-v2-*.json'))
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
        forged = json.loads(cache.read_text())
        forged['totals'] = [100, 0, 900]
        cache.write_text(json.dumps(forged))
        cache.chmod(0o666)
        self.assertIn('10.0%', self.execute('cache'))
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_invalid_json_is_quiet(self):
        self.assertEqual(self.execute(raw='{invalid'), '')

    def test_cache_percentage_includes_uncached_input(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_creation_input_tokens=0,
                                             cache_read_input_tokens=100))
        self.assertIn('10.0%', self.execute('cache'))

    def test_later_usage_update_is_not_lost_or_double_counted(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=0)
                                  + self.usage('m1', input_tokens=900, cache_read_input_tokens=100)
                                  + self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.assertIn('10.0%', self.execute('cache'))

    def test_same_size_rewrite_invalidates_cache(self):
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        self.execute('cache')
        self.transcript.write_text(self.usage('m1', input_tokens=100, cache_read_input_tokens=900))
        self.assertIn('90.0%', self.execute('cache'))

    def test_missing_uncached_input_does_not_claim_full_hit(self):
        self.transcript.write_text(self.usage('m1', cache_read_input_tokens=100))
        output = self.execute('cache')
        self.assertNotIn('100%', output)
        self.assertNotIn('100.0%', output)
        self.assertIn('未知', output)

    def test_non_assistant_and_invalid_counts_are_ignored(self):
        self.transcript.write_text(json.dumps({'type': 'user', 'message': {'role': 'user', 'usage': {
            'input_tokens': 9000, 'cache_read_input_tokens': 0}}}) + '\n'
            + self.usage('m1', input_tokens=900, cache_read_input_tokens=100)
            + self.usage('m2', input_tokens=-100, cache_read_input_tokens='bad'))
        self.assertIn('10.0%', self.execute('cache'))

    def test_oversized_adapter_input_is_quiet(self):
        self.assertEqual(self.execute(raw=' ' * (256 * 1024 + 1)), '')

    def test_non_object_adapter_input_is_quiet(self):
        self.assertEqual(self.execute(raw='[]'), '')

    def test_missing_plugin_does_not_break_cache_line(self):
        cache = Path(self.env['CLAUDE_CONFIG_DIR']) / 'plugins/cache/claude-hud/claude-hud/0.11.2'
        cache.unlink()
        self.transcript.write_text(self.usage('m1', input_tokens=900, cache_read_input_tokens=100))
        output = self.execute()
        self.assertIn('10.0%', output)
        self.assertNotIn('请求', output)

    def test_sandbox_blocks_network_and_real_home(self):
        probe = ('import os,socket\n'
                 'try:\n socket.create_connection(("127.0.0.1",9),timeout=0.2)\n'
                 'except OSError as e:\n assert e.errno in (1,13), repr(e)\n'
                 'else:\n raise AssertionError("network was allowed")\n'
                 'try:\n os.listdir(' + repr(str(REAL_HOME)) + ')\n'
                 'except PermissionError:\n pass\n'
                 'else:\n raise AssertionError("real HOME was readable")\n')
        result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(self.profile),
                                 '/usr/bin/python3', '-I', '-c', probe],
                                text=True, capture_output=True, env=self.env, cwd=self.root, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr[:700])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root', type=Path, required=True,
                        help='Installed claude-hud 0.11.2 root matching provenance.json.')
    args, remaining = parser.parse_known_args()
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        parser.error('Real-plugin tests require macOS sandbox-exec.')
    if not Path('/opt/homebrew/bin/node').is_file():
        parser.error('The archived adapter requires /opt/homebrew/bin/node.')
    PLUGIN_ROOT = args.plugin_root.expanduser().resolve()
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
