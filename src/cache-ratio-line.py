#!/usr/bin/env python3
"""Report deduplicated input token reuse, not request hits or billing savings."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

FIELDS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')


def valid_count(value):
    return type(value) is int and value >= 0


def count_usage(path):
    messages = {}
    with path.open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get('message')
            if record.get('type') != 'assistant' or not isinstance(message, dict):
                continue
            usage = message.get('usage')
            if not isinstance(usage, dict):
                continue
            counts = {key: value for key in FIELDS if valid_count(value := usage.get(key))}
            if not counts:
                continue
            identity = message.get('id') or record.get('uuid')
            if not isinstance(identity, str) or not identity:
                continue
            saved = messages.setdefault(identity, {})
            for key, value in counts.items():
                saved[key] = max(saved.get(key, 0), value)
    totals = [sum(message.get(key, 0) for message in messages.values()) for key in FIELDS]
    incomplete = any('input_tokens' not in message and any(message.get(k, 0) for k in FIELDS[1:]) for message in messages.values())
    return totals, incomplete


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, TypeError):
        return
    if not isinstance(data, dict) or not isinstance(data.get('transcript_path'), str):
        return
    path = Path(data['transcript_path'])
    try:
        stat = path.stat()
    except OSError:
        return
    signature = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]
    name = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    cache = Path(tempfile.gettempdir()) / f'cchud-cache-v2-{os.getuid()}-{name}.json'
    totals = None
    incomplete = False
    try:
        fd = os.open(cache, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd) as handle:
            info = os.fstat(handle.fileno())
            cached = json.loads(handle.read(4096)) if info.st_uid == os.getuid() and not info.st_mode & 0o077 else None
        if isinstance(cached, dict) and cached.get('signature') == signature:
            values = cached.get('totals')
            if isinstance(values, list) and len(values) == 3 and all(valid_count(v) for v in values):
                totals, incomplete = values, bool(cached.get('incomplete'))
    except (OSError, ValueError, TypeError):
        pass
    if totals is None:
        try:
            totals, incomplete = count_usage(path)
        except (OSError, ValueError, TypeError):
            return
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=cache.parent, prefix='cchud-', delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'signature': signature, 'totals': totals, 'incomplete': incomplete}, handle)
            os.replace(temporary, cache)
        except OSError:
            if 'temporary' in locals():
                temporary.unlink(missing_ok=True)
    uncached, created, read = totals
    total = sum(totals)
    if total == 0:
        return
    percent = '未知（未报告未缓存输入）' if incomplete else f'{read / total * 100:.1f}%'
    hit = read / total * 100
    color, tag = ('\033[2m', '—') if incomplete else (('\033[1;31m', '⚠低复用') if hit < 50 else (('\033[33m', '复用一般') if hit < 80 else ('\033[32m', '✓高复用')))
    ratio = '未知' if incomplete else f'{read / total:.3f}'
    def tokens(number):
        return f'{number / 1000:.1f}k' if number >= 1000 else str(number)
    print(f'{color}♻ 缓存命中 {percent} {tag}（输入token） · 命中比{ratio} (未缓存{tokens(uncached)}/写{tokens(created)}/读{tokens(read)})\033[0m')


if __name__ == '__main__':
    main()
