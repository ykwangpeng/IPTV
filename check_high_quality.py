#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对高质量来源做深度随机抽样测试"""
import requests, sys, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

s = requests.Session()
s.trust_env = False
s.headers['User-Agent'] = 'VLC/3.0.18'

SOURCES = {
    'Guovin (catvod)': 'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt',
    'q101767 (cztvcdn)': 'https://raw.githubusercontent.com/q1017673817/iptvz/refs/heads/main/zubo.txt',
    'big-mouth-cn': 'https://gh-proxy.com/https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u',
    'develop202': 'https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt',
    '264788.xyz': 'https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt',
    'gh-proxy.org': 'https://gh-proxy.org/https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1',
    '47.120.41.246': 'http://47.120.41.246:8899/xinzb.txt',
    'peterhchina': 'https://peterhchina.github.io/iptv/CNTV-V4.m3u',
    'live.zbds.top': 'https://live.zbds.top/tv/iptv4.m3u',
}

def stream_check(url, timeout=8):
    t0 = time.time()
    try:
        r = s.get(url, timeout=timeout, verify=False,
                  headers={'Range': 'bytes=0-32767', 'User-Agent': s.headers['User-Agent']})
        elapsed = time.time() - t0
        content = r.content[:300]
        ok = r.status_code in (200, 206) and (
            b'#EXTM3U' in content or b'\x47' in content[:4] or b'FLV' in content)
        return ok, r.status_code, elapsed, len(r.content)
    except Exception as e:
        return False, type(e).__name__[:15], time.time()-t0, 0

def test_source(name_url):
    name, url = name_url
    t0 = time.time()
    try:
        r = s.get(url, timeout=15, verify=False)
        elapsed = time.time() - t0
        lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        
        # 提取 URLs
        http_lines = [l for l in lines if l.startswith(('http://','https://'))]
        comma_lines = [l for l in lines if ',' in l and ',#genre#' not in l]
        
        urls_to_test = []
        if http_lines:
            # M3U 格式
            for l in http_lines[:5]:
                urls_to_test.append(l)
        elif comma_lines:
            # TXT(n) 格式
            for l in comma_lines[:5]:
                parts = l.split(',', 1)
                if len(parts) == 2 and parts[1].strip().startswith(('http://','https://')):
                    urls_to_test.append(parts[1].strip())
        
        # 随机抽取 20 个测试
        all_urls = urls_to_test.copy()
        for l in lines:
            if l.startswith(('http://','https://')):
                all_urls.append(l)
            elif ',' in l and ',#genre#' not in l:
                parts = l.split(',', 1)
                if len(parts) == 2 and parts[1].strip().startswith(('http://','https://')):
                    all_urls.append(parts[1].strip())
        
        if len(all_urls) > 30:
            sample = random.sample(all_urls, 30)
        else:
            sample = all_urls
        
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(stream_check, u): u for u in sample}
            for future in as_completed(futures):
                ok, status, elapsed, size = future.result()
                results.append((ok, status))
        
        ok_count = sum(1 for ok, _ in results if ok)
        fail_count = len(results) - ok_count
        
        return {
            'name': name, 'status': r.status_code, 'fetch_time': elapsed,
            'total_lines': len(lines), 'urls_extracted': len(all_urls),
            'tested': len(results), 'ok': ok_count, 'fail': fail_count,
            'pass_rate': ok_count/len(results)*100 if results else 0,
            'sample': sample[:5], 'error': None
        }
    except Exception as e:
        return {'name': name, 'status': 'ERR', 'error': str(e)[:60],
                'tested': 0, 'ok': 0, 'fail': 0, 'pass_rate': 0}

print('Testing high-quality sources (30 random URLs each)...')
print()

results = []
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(test_source, item): item for item in SOURCES.items()}
    for future in as_completed(futures):
        r = future.result()
        results.append(r)
        if r.get('error'):
            print('ERR  %-20s  %s' % (r['name'], r['error']))
        else:
            pr = r['pass_rate']
            bar = '#' * int(pr/5) + '-' * (20-int(pr/5))
            print('%3d%% %s  %s  %d/%d  %s' % (
                pr, bar, r['name'], r['ok'], r['tested'], r['urls_extracted']))
            # Show sample URLs
            for url in r['sample'][:2]:
                print('      %s' % url[:70])

print()
print('=== Final Ranking ===')
results.sort(key=lambda x: -x.get('pass_rate', 0))
for i, r in enumerate(results):
    if r.get('error'): continue
    pr = r['pass_rate']
    stars = '★' * int(pr/20) if pr >= 20 else '☆' if pr >= 5 else ' '
    print('%2d. %3d%% %s %-20s (%d/%d tested, %d URLs)' % (
        i+1, pr, stars, r['name'], r['ok'], r['tested'], r['urls_extracted']))
