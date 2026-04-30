import re
from collections import Counter

# 从 live_ok_fail.txt 中统计失效频道的域名
with open('live_ok_fail.txt', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 提取 URL
urls = re.findall(r'https?://[^\s,\)"]+', content)
print(f'Total failed URLs found: {len(urls)}')

# 统计域名
domains = [url.split('/')[2] for url in urls if len(url.split('/')) > 2]
top_domains = Counter(domains).most_common(15)
print('\nTop 15 domains in failed list:')
for domain, count in top_domains:
    print(f'  {domain}: {count}')

# 统计国内 vs 海外域名
cn_domains = ['cntv.cn', 'cctv.cn', 'tv.cn', 'chinamobile.com', 'chinatelecom.com.cn', 'jstv.com', 'jsbc.com', 'hunanwebtv.com', 'guangdong.cn', 'gdwl.cn', 'migu.cn']
overseas = sum(1 for d in domains if not any(cd in d for cd in cn_domains))
cn_count = len(domains) - overseas
print(f'\nApprox CN domains: {cn_count}')
print(f'Approx Overseas domains: {overseas}')
