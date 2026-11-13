#!/usr/bin/env python3
"""
Web 资源/密钥扫描器：从 HTML/JS 文件里提取 URL、key、接口路径、流媒体地址。
用法:
    python3 scan_web_assets.py <文件或目录> [--json]
输出（stdout，人类可读；--json 则 JSON）:
    domains / api_paths / keys / stream_urls / sourcemaps
"""
import re
import sys
import json
import os

URL_RE = re.compile(r'https?://[a-zA-Z0-9._\-:\[\]]+')
API_RE = re.compile(r'["\'](/[a-zA-Z][a-zA-Z0-9_\-/]{3,60})["\']')
KEY_RE = re.compile(
    r'["\']?([a-zA-Z_][a-zA-Z0-9_]{2,30})["\']?\s*[:=]\s*["\']([A-Za-z0-9+/=_\-]{16,80})["\']')
STREAM_RE = re.compile(r'https?://[^\s"\']+\.m3u8[^\s"\']*|https?://[^\s"\']+\.flv[^\s"\']*|rtmp://[^\s"\']+')
SOURCEMAP_RE = re.compile(r'//# sourceMappingURL=(\S+)')

KEY_NAMES_HINT = ('key', 'secret', 'token', 'appkey', 'app_key', 'sign', 'salt',
                  'appid', 'app_id', 'auth', 'captcha', 'password', 'apikey')


def is_noise_api(p: str) -> bool:
    noise = ('.png', '.jpg', '.css', '.js', '.gif', '.svg', '.woff', '.ico', '.mp4')
    return p.lower().endswith(noise) or len(p) < 5


def scan_file(path: str):
    try:
        src = open(path, encoding='utf-8', errors='ignore').read()
    except Exception:
        return None
    domains = set(m.group(0).rstrip('/') for m in URL_RE.finditer(src))
    apis = set(m.group(1) for m in API_RE.finditer(src) if not is_noise_api(m.group(1)))
    keys = {}
    for m in KEY_RE.finditer(src):
        name, val = m.group(1), m.group(2)
        if any(h in name.lower() for h in KEY_NAMES_HINT) and not val.startswith(('http', '/')):
            keys[name] = val
    streams = set(m.group(0) for m in STREAM_RE.finditer(src))
    sourcemaps = set(m.group(1) for m in SOURCEMAP_RE.finditer(src))
    return domains, apis, keys, streams, sourcemaps


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = sys.argv[1]
    as_json = '--json' in sys.argv

    files = []
    if os.path.isfile(target):
        files = [target]
    elif os.path.isdir(target):
        for root, _, fns in os.walk(target):
            for fn in fns:
                if fn.endswith(('.js', '.html', '.json', '.css', '.ts')):
                    files.append(os.path.join(root, fn))
    else:
        print(f'error: 不存在: {target}')
        sys.exit(1)

    domains, apis, keys, streams, sourcemaps = set(), set(), {}, set(), set()
    for f in files:
        r = scan_file(f)
        if not r:
            continue
        domains |= r[0]
        apis |= r[1]
        keys.update(r[2])
        streams |= r[3]
        sourcemaps |= r[4]

    if as_json:
        print(json.dumps({
            'files_scanned': len(files),
            'domains': sorted(domains),
            'api_paths': sorted(apis)[:200],
            'keys': keys,
            'stream_urls': sorted(streams),
            'sourcemaps': sorted(sourcemaps),
        }, ensure_ascii=False, indent=2))
        return

    print(f'== 文件数: {len(files)} ==\n')
    print(f'== 域名 ({len(domains)}) ==')
    for d in sorted(domains):
        print(' ', d)
    print(f'\n== 接口路径 (前 60 / 共 {len(apis)}) ==')
    for a in sorted(apis)[:60]:
        print(' ', a)
    print(f'\n== 疑似 key/secret ({len(keys)}) ==')
    for k, v in keys.items():
        print(f'  {k} = {v}')
    print(f'\n== 流媒体地址 ({len(streams)}) ==')
    for s in sorted(streams):
        print(' ', s[:160])
    print(f'\n== sourcemap 引用 ({len(sourcemaps)}) ==')
    for s in sorted(sourcemaps):
        print(' ', s)


if __name__ == '__main__':
    main()
