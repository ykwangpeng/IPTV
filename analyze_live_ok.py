#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 live_ok.txt 完整内容"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from urllib.parse import urlparse
from collections import Counter

# 分析 live_ok.txt
domains = Counter()
urls = []
with open(r'C:\tools\IPTV\live_ok.txt', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        if line.startswith('#'):
            print('HDR:', line[:60])
            continue
        if ',' not in line: continue
        name, url = line.split(',', 1)
        url = url.strip()
        urls.append((name.strip(), url))
        try:
            netloc = urlparse(url).netloc.lower().split(':')[0]
            domains[netloc] += 1
        except:
            domains['(parse_err)'] += 1

print()
print('=== live_ok.txt 分析 ===')
print('总频道数:', len(urls))
print()
print('域名分布:')
for d, n in domains.most_common():
    print('  %4d  %s' % (n, d))
print()
print('所有频道 URLs:')
for name, url in urls:
    try:
        netloc = urlparse(url).netloc.lower()
    except:
        netloc = 'unknown'
    print('  %-30s  %s' % (name[:30], url[:80]))

# 同时检查 live_ok_fail.txt 中是否有 live.zbds.top
print()
print('=== live_ok_fail.txt 中的 live.zbds.top 相关域名 ===')
fail_domains_all = Counter()
with open(r'C:\tools\IPTV\live_ok_fail.txt', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        if ',' not in line: continue
        _, url = line.split(',', 1)
        url = url.strip()
        try:
            netloc = urlparse(url).netloc.lower().split(':')[0]
            fail_domains_all[netloc] += 1
        except:
            pass

zbds_related = [(d, n) for d, n in fail_domains_all.most_common() 
                  if any(x in d for x in ['zbds', 'zhi35', '264788', 'dsj', 'goodiptv', 'aliyun', 'alicdn', 'cztv', 'cztvcloud'])]
if zbds_related:
    for d, n in zbds_related:
        print('  %4d  %s' % (n, d))
else:
    print('  (none found)')

# 检查 paste.txt 中 live.zbds.top 相关域名的状态
print()
print('=== paste.txt 中 live.zbds.top 域名分布 ===')
paste_domains = Counter()
with open(r'C:\tools\IPTV\paste.txt', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        if ',' not in line: continue
        _, url = line.split(',', 1)
        url = url.strip()
        if not url.startswith(('http://', 'https://')): continue
        try:
            netloc = urlparse(url).netloc.lower().split(':')[0]
            paste_domains[netloc] += 1
        except:
            pass

zbds_paste = [(d, n) for d, n in paste_domains.most_common()
              if any(x in d for x in ['zbds', 'zhi35', '264788', 'dsj', 'goodiptv', 'aliyun', 'alicdn', 'cztvcloud', 'tvpull'])]
print('Total live.zbds.top related domains in paste.txt:')
for d, n in zbds_paste:
    in_ok = d in domains
    in_fail = fail_domains_all.get(d, 0)
    print('  %4d  %s  ok=%d fail=%d' % (n, d, in_ok, in_fail))
