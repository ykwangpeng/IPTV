import os

# 搜索 load_from_file 的调用
for root, dirs, files in os.walk('C:\\tools\\IPTV\\iptv_apex'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if 'load_from_file' in content and 'def load_from_file' not in content:
                print(f"Found in: {filepath}")
                for i, line in enumerate(content.split('\n'), 1):
                    if 'load_from_file' in line and 'def ' not in line:
                        print(f"  Line {i}: {line.strip()}")
