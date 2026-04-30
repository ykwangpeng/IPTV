#!/usr/bin/env python3
"""快速测试源质量"""
import requests
import random
import urllib3
urllib3.disable_warnings()

def test_source(name, url):
    print(f"\n{name}")
    try:
        r = requests.get(url, timeout=15, verify=False)
        if r.status_code != 200:
            print(f"  FAIL: HTTP {r.status_code}")
            return

        content = r.content
        # 解析频道
        urls = []
        for line in content.decode('utf-8', errors='ignore').split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)

        print(f"  Channels: {len(urls)}")

        if len(urls) == 0:
            return

        # 抽样测试 10 个
        samples = random.sample(urls, min(10, len(urls)))
        ok = 0
        for u in samples:
            try:
                r2 = requests.head(u, headers={'User-Agent': 'VLC/3.0.18', 'Range': 'bytes=0-511'},
                                   timeout=5, verify=False, allow_redirects=True)
                if r2.status_code in [200, 206]:
                    ok += 1
            except:
                pass

        rate = ok / len(samples) * 100
        print(f"  Test: {ok}/{len(samples)} OK ({rate:.1f}%)")
        if rate >= 50:
            print(f"  >>> RECOMMENDED: {url}")

    except Exception as e:
        print(f"  FAIL: {e}")

# 测试源
SOURCES = [
    ("hujingguang/Global", "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Global.m3u8"),
    ("hujingguang/HK", "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8"),
    ("hujingguang/TW", "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8"),
    ("zhangbin0301/iptv4", "https://raw.githubusercontent.com/zhangbin0301/iptv2025/master/tv/iptv4.m3u"),
    ("live.hacks/ipv4", "https://live.hacks.tools/tv/ipv4/categories/地方频道.txt"),
]

print("Quick Test - GitHub IPTV Sources")
print("="*50)

for name, url in SOURCES:
    test_source(name, url)
