#!/usr/bin/env python3
"""Render the installed HUD with explicit custom-provider metric boundaries."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlparse


def text(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', value)
    return ''.join(c for c in value if not unicodedata.category(c).startswith('C'))[:80]


def positive_int(value):
    try:
        number = int(value)
        return number if 1000 <= number <= 10000000 else None
    except (ValueError, TypeError):
        return None


def token_count(value):
    return value if type(value) is int and value >= 0 else 0


def main():
    raw = sys.stdin.read(256 * 1024 + 1)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return
    if not isinstance(data, dict) or len(raw) > 256 * 1024:
        return
    base = os.environ.get('ANTHROPIC_BASE_URL', '')
    hostname = urlparse(base).hostname
    proxied = bool(hostname and hostname not in {'api.anthropic.com', 'api.us.anthropic.com'})
    if proxied:
        model = data.get('model')
        if isinstance(model, dict):
            model['display_name'] = '请求 ' + text(model.get('id') or model.get('display_name'))
            family = next((f for f in ['OPUS', 'SONNET', 'HAIKU', 'FABLE'] if f.lower() in str(model.get('id', '')).lower()), None)
            configured = text(os.environ.get(f'ANTHROPIC_DEFAULT_{family}_MODEL_NAME', '')) if family else ''
            if configured:
                model['display_name'] += ' · 配置名 ' + configured
        capacity = positive_int(os.environ.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS'))
        window = data.get('context_window')
        if capacity and isinstance(window, dict):
            window['context_window_size'] = capacity
            usage = window.get('current_usage')
            keys = ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens']
            reported = isinstance(usage, dict) and type(usage.get('input_tokens')) is int and usage['input_tokens'] >= 0
            if reported:
                reported = all(usage.get(k) is None or (type(usage[k]) is int and usage[k] >= 0) for k in keys)
            if reported:
                tokens = sum(token_count(usage.get(k)) for k in keys)
                window['used_percentage'] = min(100, tokens * 100 / capacity)
            else:
                window['current_usage'] = None
                window['used_percentage'] = None
                if isinstance(model, dict):
                    model['display_name'] += ' · usage待报告'
        data.pop('rate_limits', None)
        data.pop('prompt_cache', None)
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR') or str(Path.home() / '.claude'))
    root = config / 'plugins/cache/claude-hud/claude-hud'
    versions = [p for p in root.glob('*') if re.fullmatch(r'\d+\.\d+\.\d+', p.name) and (p / 'dist/index.js').is_file()]
    encoded = json.dumps(data, ensure_ascii=False)
    if versions:
        plugin = max(versions, key=lambda p: tuple(int(v) for v in p.name.split('.')))
        try:
            result = subprocess.run(['/opt/homebrew/bin/node', str(plugin / 'dist/index.js')], input=encoded,
                                    text=True, capture_output=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.rstrip()[:32768]
                if proxied:
                    output = re.sub(r'(Cost|Today|Week|费用|成本|今日|本周)\s+\$\d+(?:\.\d+)?', r'\1 实付未知', output)
                print(output)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        result = subprocess.run(['/usr/bin/python3', '-I', str(Path.home() / '.claude/cache-ratio-line.py')],
                                input=encoded, text=True, capture_output=True, timeout=3)
        if result.returncode == 0 and result.stdout.strip():
            print(result.stdout.rstrip()[:2048])
    except (OSError, subprocess.TimeoutExpired):
        pass


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError):
        pass
