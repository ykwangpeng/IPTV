#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度分析新来源的实际格式和可用性"""
import requests, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

s = requests.Session()
s.trust_env = False
s.headers['User-Agent'] = 'VLC/3.0.18'

SOURCES = [
    ('47.120.41.246', 'http://47.120.41.246:8899/xinzb.txt'),
    ('tvv.tw/proxy',  'https://tvv.tw/https://raw.githubusercontent.com/tushen6/xxooo/refs/heads/main/TV/lzxw.txt'),
    ('264788.xyz',    'https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt'),
    ('feer-cdn',      'https://feer-cdn-bp.xpnb.qzz.io/xnkl.txt'),
    ('gc.gt.tc',      'http://gc.gt.tc/o/i/HKTV.txt'),
    ('Guovin',        'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt'),
    ('q101767',       'https://raw.githubusercontent.com/q1017673817/iptvz/refs/heads/main/zubo.txt'),
    ('gh-proxy.org',  'https://gh-proxy.org/https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1'),
    ('zxmlxw520',     'https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt'),
    ('down.nigx.cn',  'https://down.nigx.cn/raw.githubusercontent.com/fafa002/yf2025/refs/heads/main/yiyifafa.txt'),
    ('big-mouth-cn',  'https://gh-proxy.com/https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u'),
    ('develop202',    'https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt'),
]

def fetch_content(name_url):
    name, url = name_url
    t0 = time.time()
    try:
        r = s.get(url, timeout=15, verify=False)
        elapsed = time.time() - t0
        lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        
        # 格式分析
        http_starts = [l for l in lines if l.startswith(('http://','https://'))]
        comma_lines = [l for l in lines if ',' in l]
        genre_lines = [l for l in lines if ',#genre#' in l]
        extm3u_lines = [l for l in lines if '#EXTM3U' in l]
        
        # 从 TXT 格式提取 URL（name,http://URL 格式）
        txt_urls = []
        for l in comma_lines:
            if ',#genre#' in l: continue
            parts = l.split(',', 1)
            if len(parts) == 2:
                url_part = parts[1].strip()
                if url_part.startswith(('http://','https://')):
                    txt_urls.append((parts[0].strip(), url_part))
        
        # 检测格式
        if extm3u_lines:
            fmt = 'M3U'
        elif txt_urls and not http_starts:
            fmt = 'TXT(n)'
        elif http_starts:
            fmt = 'M3U/d'
        else:
            fmt = '???'
        
        return {
            'name': name, 'status': r.status_code, 'elapsed': elapsed,
            'size': len(r.text), 'lines': len(lines),
            'http_starts': len(http_starts), 'comma': len(comma_lines),
            'genre': len(genre_lines), 'extm3u': len(extm3u_lines),
            'txt_urls': txt_urls, 'http_start_lines': http_starts,
            'all_lines': lines[:20], 'fmt': fmt, 'error': None
        }
    except Exception as e:
        return {'name': name, 'status': 'ERR', 'elapsed': time.time()-t0, 
                'error': str(e)[:60], 'size': 0, 'lines': 0}

def test_urls(urls):
    """并发测试 URLs 的有效性"""
    def _test(name_url):
        name, url = name_url
        t0 = time.time()
        try:
            r = s.get(url, timeout=5, verify=False,
                      headers={'Range': 'bytes=0-511'})
            elapsed = time.time() - t0
            content = r.content[:200]
            ok = r.status_code in (200, 206) and (
                b'#EXTM3U' in content or b'\x47' in content[:4] or b'FLV' in content)
            return (name, url, 'OK' if ok else 'XX:%d' % r.status_code, elapsed)
        except Exception as e:
            return (name, url, 'ERR', time.time()-t0)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_test, urls))
    return results

print('Fetching and analyzing %d sources...' % len(SOURCES))
print()
results = []
for name, url in SOURCES:
    r = fetch_content((name, url))
    results.append(r)
    
    if r.get('error'):
        print('ERR %s  %s' % (r['name'], r['error']))
        continue
    
    print('[%s] %s %d %dB %d lines  http_start=%d comma=%d txt_urls=%d fmt=%s' % (
        r['name'], r['status'], r['elapsed'], r['size'], r['lines'],
        r['http_starts'], r['comma'], len(r['txt_urls']), r['fmt']))
    
    # 打印前几行
    for l in r['all_lines'][:5]:
        print('  > ' + repr(l[:80]))
    
    # 测试 URLs
    test_list = []
    if r['txt_urls']:
        test_list = r['txt_urls'][:3]
    elif r['http_start_lines']:
        test_list = [(l.split(',')[0][:20], l) for l in r['http_start_lines'][:3]]
    
    if test_list:
        test_results = test_urls(test_list)
        for tr in test_results:
            print('    TEST: %s %s' % (tr[2], tr[1][:70]))
    print()

# 汇总
print()
print('=' * 60)
print('Sources with playable URLs (>= 1 OK):')
for r in results:
    if r.get('error'): continue
    if r['txt_urls'] or r['http_starts']:
        print('  [%s] %s (%dB, %d URLs, fmt=%s)' % (
            'GOOD' if r['txt_urls'] else '??', r['name'], r['size'],
            max(len(r['txt_urls']), r['http_starts']), r['fmt']))
