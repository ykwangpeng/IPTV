import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查剩余乱码
with open('C:\\tools\\IPTV\\live_ok.txt', 'r', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f):
        if 'æ²³åç§»å¨' in line or 'åç§»å¨' in line:
            print(f"Line {i+1}: {line.strip()[:100]}")
