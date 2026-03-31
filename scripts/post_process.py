import os
if not os.path.exists('live_ok.txt'): 
    print("No file")
    exit(0)
with open('live_ok.txt', 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if ',' in l.strip()]
# Dedupe: max 3 sources per channel name
channels = {}
for line in lines:
    parts = line.split(',', 1)
    if len(parts) != 2: continue
    name, url = parts
    name = name.strip()
    if name not in channels: channels[name] = []
    if len(channels[name]) < 3: channels[name].append((name, url))
# Chinese priority
def chinese_priority(name):
    cn_kw = ['CCTV', 'TVB', 'ATV', 'News', 'Sports', 'Kids', 'Movie', 'Drama',
             'Beijing', 'Shanghai', 'Guangdong', 'Zhejiang', 'Jiangsu', 'Hunan',
             'Taiwan', 'Hong Kong', 'Macau']
    for kw in cn_kw:
        if kw.lower() in name.lower(): return 0
    return 1
all_sources = [(chinese_priority(n), n, u) for n, urls in channels.items() for n, u in urls]
all_sources.sort(key=lambda x: (x[0], x[1]))
with open('live_ok.txt', 'w', encoding='utf-8') as f:
    for _, n, u in all_sources[:2000]: f.write(f'{n},{u}\n')
print(f'Post-process: {len(all_sources[:2000])} sources (Chinese: {sum(1 for x in all_sources[:2000] if x[0]==0)})')