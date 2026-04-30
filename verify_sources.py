#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速验证所有订阅源的实际可用性"""
import requests, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

s = requests.Session()
s.trust_env = False
s.headers['User-Agent'] = 'VLC/3.0.18 LibVLC/3.0.18'

sources = [
    'https://live.zbds.top/tv/iptv4.m3u',
    'https://live.zbds.top/tv/iptv4.txt',
    'https://live.zhi35.com/iptv.m3u',
    'https://peterhchina.github.io/iptv/CNTV-V4.m3u',
    'https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt',
    'https://live.hacks.tools/tv/ipv4/categories/cn.m3u',
    'https://live.hacks.tools/tv/ipv4/categories/hk.m3u',
    'https://live.hacks.tools/tv/ipv4/categories/mo.m3u',
    'https://live.hacks.tools/tv/ipv4/categories/tw.m3u',
    'https://live.hacks.tools/tv/ipv4/categories/少儿.txt',
    'https://zxmlxw520.github.io/tv/live.txt',
    'https://raw.githubusercontent.com/litywang/IPTV/main/live_ok.txt',
]

print('Source  | Status | Time | Size | Format | HTTP_urls | Valid_test')
print('-' * 80)

for url in sources:
    t0 = time.time()
    try:
        r = s.get(url, timeout=10, verify=False)
        elapsed = time.time() - t0
        content = r.text
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        http_lines = [l for l in lines if l.startswith('http://') or l.startswith('https://')]
        txt_lines = [l for l in lines if ',' in l and not l.startswith('http')]
        genre_lines = [l for l in lines if ',#genre#' in l]
        is_m3u = any('#EXTINF' in l for l in lines[:5])
        
        # Test first HTTP URL
        first_http = None
        if http_lines:
            first_http = http_lines[0].split(',')[-1].strip() if ',' in http_lines[0] else http_lines[0]
        elif txt_lines:
            first_http = txt_lines[0].split(',')[-1].strip()
        
        test_result = 'N/A'
        if first_http and first_http.startswith('http'):
            t1 = time.time()
            try:
                r2 = s.get(first_http, timeout=5, verify=False,
                           headers={'Range':'bytes=0-511'})
                content2 = r2.content[:100]
                ok = r2.status_code in (200,206) and (b'#EXTM3U' in content2 or b'\x47' in content2[:4] or b'FLV' in content2)
                test_result = 'OK' if ok else 'XX:%d' % r2.status_code
            except Exception as e:
                test_result = 'ERR:' + type(e).__name__[:10]
        
        fmt = 'M3U' if is_m3u else ('TXT' if txt_lines else '???')
        print('%-35s %-6s %4.1fs %7dB %-4s %3d+%3d %s' % (
            url[:35], r.status_code, elapsed, len(content), fmt,
            len(http_lines), len(txt_lines), test_result))
    except Exception as e:
        print('%-35s %-20s' % (url[:35], 'ERR:' + type(e).__name__[:18]))
