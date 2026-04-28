# -*- coding: utf-8 -*-
"""分析 live_ok.txt 的频道来源分布"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from urllib.parse import urlparse
from collections import Counter, defaultdict

# 加载所有频道
channels = {}  # name -> [urls]
with open('live_ok.txt', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or ',' not in line:
            continue
        parts = line.split(',', 1)
        name = parts[0]
        url = parts[1].strip()
        channels.setdefault(name, []).append(url)

print(f"总频道数: {len(channels)}")
print(f"总URL数:  {sum(len(v) for v in channels.values())}")
print()

# 分类：1=国内直接访问 2=国内需代理 3=海外不可用 4=未知
china_direct = []  # 国内直连（腾讯云、阿里云、国内CDN等）
china_proxy = []   # 国内但需要代理（IP:PORT商业源等）
overseas = []      # 海外/不确定
unknown = []

KNOWN_CHINA = {
    'tencentplay', 'gztv', 'bestv', 'bp-resource', 'amucn', 'xryo',
    'kmdns', 'migu', 'dsj', 'dsj10', 'dsj-131', 'ottiptv', 'iill',
    '163189', 'jdshipin', 'aliyun', 'alicdn', 'ali-cdn', 'cztv',
    'speedws', 'tencent', 'tx', 'cos', 'myqcloud',
    '264788', 'live.264788', 'live.ottiptv',
    'cdn8', 'cdn6', 'cdn12', 'cdn.',  # 各种国内CDN
    'goodiptv',  # 国内商业源，端口访问
    'mobai', 'mobaibox', 'ott.mobaibox',
    'aktv', '061833', '888', '8888', '2096', '555',
}

KNOWN_OVERSEAS = {
    'freetv.fun', 'iptv.fr', 'stream.hrbtv', 'litv', 'speedws.com',
    'cloudfront', 'indevs', 'streaming', 'pp.ua', 'us.kg', 'dxjc',
    'ali-cdn', 'myalicdn', 'cztv', 'aliyun',
}

domain_stats = Counter()
china_ok = Counter()
china_proxy_count = Counter()
overseas_count = Counter()
other_count = Counter()

for name, urls in channels.items():
    for url in urls:
        try:
            netloc = urlparse(url).netloc.lower()
            domain = netloc.split(':')[0]
            domain_stats[domain] += 1
            
            # 判断
            if any(k in netloc for k in KNOWN_CHINA):
                china_ok[domain] += 1
            elif any(k in netloc for k in KNOWN_OVERSEAS):
                overseas_count[domain] += 1
            elif domain[0].isdigit():
                # IP地址
                if domain.startswith(('10.', '192.', '172.')):
                    china_ok[domain] += 1
                else:
                    china_proxy_count[domain] += 1
            elif '.' in domain:
                overseas_count[domain] += 1
            else:
                other_count[domain] += 1
        except:
            other_count['<parse_error>'] += 1

total_china_ok = sum(china_ok.values())
total_china_proxy = sum(china_proxy_count.values())
total_overseas = sum(overseas_count.values())
total_other = sum(other_count.values())

total_all = total_china_ok + total_china_proxy + total_overseas + total_other
denom = max(total_all, 1)

print(f"=== 来源分类统计 ===")
print(f"国内直连: {total_china_ok} ({total_china_ok*100//denom}%)")
print(f"国内IP商业源: {total_china_proxy} ({total_china_proxy*100//denom}%)")
print(f"海外/未知: {total_overseas} ({total_overseas*100//denom}%)")
print()

print(f"=== 国内直连源 TOP 20 ===")
for d, n in china_ok.most_common(20):
    print(f"  {n:4d}  {d}")

print()
print(f"=== 国内IP商业源 (可能被墙) ===")
for d, n in china_proxy_count.most_common(20):
    print(f"  {n:4d}  {d}")

print()
print(f"=== 海外/未知源 ===")
for d, n in overseas_count.most_common(20):
    print(f"  {n:4d}  {d}")
