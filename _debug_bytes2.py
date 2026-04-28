import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查特定行的原始字节
with open('C:\\tools\\IPTV\\live_ok.txt', 'rb') as f:
    lines = f.readlines()
    
# 查找包含乱码的行
for i, line in enumerate(lines):
    if b'\xc3\xa5' in line or b'\xc2\xa8' in line:
        print(f"Line {i+1} raw bytes: {line[:80]}")
        print(f"Line {i+1} as utf-8: {line.decode('utf-8', errors='replace')[:80]}")
        print()
        if i > 10:
            break
