import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fix_url_param(text):
    """修复 URL 参数中的乱码"""
    # 这些乱码是 URL 参数的一部分，不影响播放
    # 但为了美观，我们可以尝试修复
    try:
        return text.encode('latin-1').decode('utf-8')
    except:
        return text

# 修复 live_ok.txt
fixed_lines = []
with open('C:\\tools\\IPTV\\live_ok.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        fixed = fix_url_param(line)
        fixed_lines.append(fixed)

with open('C:\\tools\\IPTV\\live_ok.txt', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed URL parameters in live_ok.txt")

# 修复 live_ok.m3u
fixed_lines = []
with open('C:\\tools\\IPTV\\live_ok.m3u', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        fixed = fix_url_param(line)
        fixed_lines.append(fixed)

with open('C:\\tools\\IPTV\\live_ok.m3u', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed URL parameters in live_ok.m3u")
