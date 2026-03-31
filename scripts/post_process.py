import os
if not os.path.exists('live_ok.txt'): 
    print("No file")
    exit(0)

# 读取文件，保留分组结构
with open('live_ok.txt', 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]

# 解析分组结构
groups = []  # [(group_name, [(name, url), ...])]
current_group = None
current_channels = {}

for line in lines:
    if line.endswith(',#genre#'):
        # 保存上一个分组
        if current_group is not None and current_channels:
            groups.append((current_group, list(current_channels.items())))
        # 开始新分组
        current_group = line.replace(',#genre#', '')
        current_channels = {}
    elif ',' in line:
        parts = line.split(',', 1)
        if len(parts) != 2: continue
        name, url = parts
        name = name.strip()
        url = url.strip()
        if not name or not url: continue
        # 去重：每个频道名最多保留 3 个源
        if name not in current_channels:
            current_channels[name] = []
        if len(current_channels[name]) < 3:
            current_channels[name].append(url)

# 保存最后一个分组
if current_group is not None and current_channels:
    groups.append((current_group, list(current_channels.items())))

# 写入文件，保留分组结构
total_count = 0
with open('live_ok.txt', 'w', encoding='utf-8') as f:
    for group_name, channels in groups:
        f.write(f'{group_name},#genre#\n')
        for name, urls in channels:
            for url in urls:
                f.write(f'{name},{url}\n')
                total_count += 1

print(f'Post-process: {total_count} sources in {len(groups)} groups')