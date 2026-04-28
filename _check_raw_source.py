import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查原始源文件中是否有乱码
with open('C:\\tools\\IPTV\\live_ok.txt', 'r', encoding='utf-8', errors='strict') as f:
    for i, line in enumerate(f):
        if i >= 50:
            break
        # 检查是否有乱码特征
        if any(ord(c) > 0x7f and ord(c) < 0x4e00 for c in line):
            print(f"Line {i}: {line.strip()}")
