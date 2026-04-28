import sys
sys.path.insert(0, 'C:\\tools\\IPTV')

# 检查源文件编码
import chardet

with open('C:\\tools\\IPTV\\live_ok.txt', 'rb') as f:
    raw = f.read(10000)
    result = chardet.detect(raw)
    print(f"Detected encoding: {result}")

# 显示前几个字节
print(f"First 100 bytes: {raw[:100]}")
