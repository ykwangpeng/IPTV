import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fix_mojibake(text):
    """修复 UTF-8 被错误编码为 Latin-1 的乱码"""
    try:
        # 先尝试用 latin-1 解码，再用 utf-8 编码
        # 但这会失败，因为乱码是双重编码
        # 正确的做法是：将乱码字符串当作 bytes 处理
        # 例如：'å\x9b\x9b' -> b'\xc3\xa5\xc2\x9b\xc2\x9b' -> 无法直接修复
        
        # 实际乱码模式：UTF-8 bytes 被当作 Latin-1 解码
        # 例如：b'\xe5\x9b\x9b' (四) -> 被当作 latin-1 -> 'å\x9b\x9b' -> 再 utf-8 encode -> b'\xc3\xa5\xc2\x9b\xc2\x9b'
        
        # 修复方法：将字符串 encode 为 latin-1，再 decode 为 utf-8
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

# 修复 live_ok.txt
fixed_lines = []
with open('C:\\tools\\IPTV\\live_ok.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        fixed = fix_mojibake(line)
        fixed_lines.append(fixed)

# 写回
with open('C:\\tools\\IPTV\\live_ok.txt', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed live_ok.txt")

# 修复 live_ok.m3u
fixed_lines = []
with open('C:\\tools\\IPTV\\live_ok.m3u', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        fixed = fix_mojibake(line)
        fixed_lines.append(fixed)

with open('C:\\tools\\IPTV\\live_ok.m3u', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed live_ok.m3u")
