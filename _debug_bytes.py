import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查特定行的原始字节
with open('C:\\tools\\IPTV\\live_ok.txt', 'rb') as f:
    lines = f.readlines()
    
# 第5行（索引4）
line5 = lines[4]
print(f"Line 5 raw bytes: {line5[:50]}")
print(f"Line 5 as utf-8: {line5.decode('utf-8', errors='replace')[:50]}")
print(f"Line 5 as latin-1: {line5.decode('latin-1', errors='replace')[:50]}")
