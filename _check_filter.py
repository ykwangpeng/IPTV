import os

# 手动搜索 VOD_DOMAINS 的使用
for root, dirs, files in os.walk('C:\\tools\\IPTV\\iptv_apex'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if 'VOD_DOMAINS' in content:
                print(f"Found in: {filepath}")
                # 显示相关行
                for i, line in enumerate(content.split('\n'), 1):
                    if 'VOD_DOMAINS' in line:
                        print(f"  Line {i}: {line.strip()}")
