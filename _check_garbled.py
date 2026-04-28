import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查乱码行
garbled_count = 0
with open('C:\\tools\\IPTV\\live_ok.txt', 'r', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f):
        # 检查是否有乱码特征（UTF-8被错误编码为Latin-1的特征）
        if 'Ã' in line or 'Â' in line or 'ä¸' in line or 'å' in line:
            garbled_count += 1
            if garbled_count <= 20:
                print(f"Line {i+1}: {line.strip()}")

print(f"\nTotal garbled lines: {garbled_count}")
