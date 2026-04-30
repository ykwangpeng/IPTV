#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测新频道列表的质量"""
import requests, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

s = requests.Session()
s.trust_env = False
s.headers['User-Agent'] = 'VLC/3.0.18'

URLS = [
    'https://tvv.tw/https://raw.githubusercontent.com/tushen6/xxooo/refs/heads/main/TV/lzxw.txt',
    'https://gh-proxy.com/https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u',
    'https://raw.githubusercontent.com/FGBLH/FG/refs/heads/main/%E6%B8%85%E5%8F%B0%E5%A4%A7%E9%99%86',
    'https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt',
    'https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt',
    'http://47.120.41.246:8899/xinzb.txt',
    'https://feer-cdn-bp.xpnb.qzz.io/xnkl.txt',
    'http://gc.gt.tc/o/i/HKTV.txt',
    'https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt',
    'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt',
    'https://gh-proxy.org/https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1',
    'https://raw.githubusercontent.com/q1017673817/iptvz/refs/heads/main/zubo.txt',
    'https://down.nigx.cn/raw.githubusercontent.com/fafa002/yf2025/refs/heads/main/yiyifafa.txt',
    'https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt',
]

def check_source(url):
    t0 = time.time()
    try:
        r = s.get(url, timeout=15, verify=False, allow_redirects=True)
        elapsed = time.time() - t0
        content = r.text
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        
        # Count URLs
        http_lines = [l for l in lines if l.startswith('http://') or l.startswith('https://')]
        comma_lines = [l for l in lines if ',' in l and not l.startswith('http')]
        genre_lines = [l for l in lines if ',#genre#' in l]
        extm3u_lines = [l for l in lines if '#EXTM3U' in l]
        
        # Format detection
        has_m3u = any('#EXTINF' in l for l in lines[:10])
        has_txt_comma = bool(comma_lines and not genre_lines)
        
        # Test first 3 HTTP URLs for validity
        test_results = []
        test_urls = []
        for l in http_lines[:3]:
            url_part = l.split(',')[-1].strip() if ',' in l else l
            if url_part.startswith('http'):
                test_urls.append(url_part)
        
        for test_url in test_urls[:2]:
            t1 = time.time()
            try:
                r2 = s.get(test_url, timeout=5, verify=False,
                           headers={'Range': 'bytes=0-511'})
                elapsed2 = time.time() - t1
                content2 = r2.content[:200]
                ok = r2.status_code in (200, 206) and (
                    b'#EXTM3U' in content2 or b'\x47' in content2[:4] or b'FLV' in content2)
                test_results.append(('OK' if ok else 'XX:%d' % r2.status_code))
            except Exception as e:
                test_results.append('ERR')
        
        fmt = 'M3U' if has_m3u else ('TXT' if has_txt_comma else '???')
        quality = '?' * sum(1 for x in test_results if x == 'OK')
        
        summary = '%-4s %3d URLs %s [%s]' % (
            fmt, len(http_lines), ' '.join(test_results) if test_results else 'N/A', quality)
        
        return (url, r.status_code, elapsed, len(content), summary, None)
    except Exception as e:
        return (url, 'ERR:'+type(e).__name__, time.time()-t0, 0, 'FETCH_FAIL', str(e)[:50])

print('Fetching %d sources concurrently...' % len(URLS))
print()

results = []
with ThreadPoolExecutor(max_workers=6) as pool:
    futures = {pool.submit(check_source, url): url for url in URLS}
    for future in as_completed(futures):
        r = future.result()
        results.append(r)
        status_str = str(r[1])[:6]
        print('%-6s %.1fs %6dB  %s' % (status_str, r[2], r[3], r[0][:60]))
        print('         %s' % r[4])
        print()

# Summary
print('=== Summary ===')
good = [r for r in results if r[4].count('OK') >= 1 and isinstance(r[1], int)]
bad = [r for r in results if r[1] == 'FETCH_FAIL' or r[4].count('OK') == 0]
print('Good sources (%d):' % len(good))
for r in good:
    print('  - %s' % r[0])
print()
print('Bad sources (%d):' % len(bad))
for r in bad:
    print('  - %s  (%s)' % (r[0][:50], r[4]))
