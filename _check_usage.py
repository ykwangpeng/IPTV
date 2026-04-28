import os

# 搜索 is_vod_domain 的使用
for root, dirs, files in os.walk('C:\\tools\\IPTV\\iptv_apex'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if 'is_vod_domain' in content:
                print(f"Found in: {filepath}")
                for i, line in enumerate(content.split('\n'), 1):
                    if 'is_vod_domain' in line:
                        print(f"  Line {i}: {line.strip()}")
