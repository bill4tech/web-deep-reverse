#!/usr/bin/env python3
"""
CDN auth_key 签名生成器（阿里云 CDN Type-A 鉴权，斗球体育实证）。
用法:
    python3 cdn_sign.py <path> <token> [--ts-offset 3600] [--url BASE]
示例:
    python3 cdn_sign.py /live/room/pull/info JmQ8uEKn6g96nSsWccw --url https://api.example.com
    # → https://api.example.com/live/room/pull/info&auth_key=1787069288-0-0-ff77038...
注意:
    - path 必须不含 query（只到 ? 前），query 不参与签名
    - ts = 当前时间 + offset（默认 3600 秒，即 1 小时有效期）
"""
import hashlib
import time
import argparse


def sign(path: str, token: str, ts_offset: int = 3600):
    ts = int(time.time()) + ts_offset
    raw = f"{path}-{ts}-0-0-{token}"
    md5 = hashlib.md5(raw.encode()).hexdigest()
    return ts, md5, f"{ts}-0-0-{md5}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="签名目标 path（不含 query）")
    ap.add_argument("token", help="CDN 防盗链 token（域池下发或 JS 硬编码）")
    ap.add_argument("--ts-offset", type=int, default=3600, help="时间戳偏移秒数，默认 3600")
    ap.add_argument("--url", default=None, help="可选：拼出完整 URL 的 base")
    args = ap.parse_args()

    path = args.path.split("?")[0]  # 强制去掉 query
    ts, md5, auth_key = sign(path, args.token, args.ts_offset)
    print(f"path     : {path}")
    print(f"ts       : {ts}")
    print(f"md5      : {md5}")
    print(f"auth_key : {auth_key}")
    if args.url:
        base_only = args.url.split("?")[0]
        query = args.url.split("?", 1)[1] if "?" in args.url else ""
        # base 已含 path → 直接在 base 上追加；否则拼 path
        if base_only.rstrip("/").endswith(path.rstrip("/")):
            url = f"{args.url}&auth_key={auth_key}" if query else f"{args.url}?auth_key={auth_key}"
        else:
            url = f"{args.url}{path}?auth_key={auth_key}"
        print(f"url      : {url}")


if __name__ == "__main__":
    main()
