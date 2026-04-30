#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 live.zbds.top 和 sync_fetcher 的实际处理结果"""
import requests, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
s = requests.Session()
s.trust_env = False
s.headers['User-Agent'] = 'VLC/3.0.18'

def check_url(url, timeout=5):
    t0 = __import__('time').time()
    try:
        r = s.get(url, timeout=timeout, verify=False,
                  headers={'Range':'bytes=0-511','User-Agent':s.headers['User-Agent']})
        elapsed = time.time() - t0
        content = r.content[:200]
        ok = r.status_code in (200,206) and (b'#EXTM3U' in content or b'\x47' in content[:4] or b'FLV' in content)
        return r.status_code, elapsed, len(r.content), ok
    except Exception as e:
        return 'ERR:'+type(e).__name__, time.time()-t0, 0, False

import time

# 1. 检查 live.zbds.top/tv/iptv4.txt 的实际格式
print('=== live.zbds.top/tv/iptv4.txt 格式分析 ===')
r = s.get('https://live.zbds.top/tv/iptv4.txt', timeout=10, verify=False)
content = r.text
lines = [l.strip() for l in content.splitlines() if l.strip()]
print('Total lines: %d, Size: %d bytes' % (len(lines), len(content)))
print('First 15 lines:')
for i, l in enumerate(lines[:15]):
    has_http = l.startswith('http://') or l.startswith('https://')
    has_comma = ',' in l
    print('  [%2d] http=%d comma=%d len=%3d %s' % (i, has_http, has_comma, len(l), repr(l[:80])))

# 2. 模拟 sync_fetcher 对 m3u 的处理
print()
print('=== live.zbds.top/tv/iptv4.m3u sync_fetcher 模拟 ===')
r2 = s.get('https://live.zbds.top/tv/iptv4.m3u', timeout=10, verify=False)
content2 = r2.text
lines2 = [l.strip() for l in content2.splitlines() if l.strip()]
http_urls = [l for l in lines2 if l.startswith('http://') or l.startswith('https://')]
print('Total lines: %d, HTTP URLs: %d' % (len(lines2), len(http_urls)))

# 提取前 3 个 HTTP URL 并测试
print('Testing first 3 HTTP URLs from m3u:')
for url in http_urls[:3]:
    status, elapsed, size, ok = check_url(url)
    print('  [%s] %s %.1fs size=%d ok=%d' % (status, url[:60], elapsed, size, ok))

# 3. 批量测试来自 m3u 的 CDN URLs
print()
print('=== 批量测试 live.zbds.top m3u CDN URLs (10 samples) ===')
ok_count = 0; fail_count = 0
for url in http_urls[:10]:
    status, elapsed, size, ok = check_url(url)
    print(('OK' if ok else 'XX') + ' %s %s' % (status, url[:60]))
    if ok: ok_count += 1
    else: fail_count += 1
print('Summary: %d OK, %d FAIL' % (ok_count, fail_count))

# 4. 检查 goodiptv.club 的 URL
print()
print('=== goodiptv.club URL 格式 ===')
# 先获取频道列表
r3 = s.get('https://live.zbds.top/tv/iptv4.m3u', timeout=10, verify=False)
content3 = r3.text
lines3 = [l.strip() for l in content3.splitlines() if l.strip()]
goodiptv_lines = [l for l in lines3 if 'goodiptv' in l.lower()]
print('Lines with goodiptv: %d' % len(goodiptv_lines))
for l in goodiptv_lines[:3]:
    print('  ', l[:80])
