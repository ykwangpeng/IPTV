import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, 'C:\\tools\\IPTV')

from iptv_apex.utils.name import NameProcessor

# 测试乱码频道名
test_names = [
    "äºåé³ä¹å¹¿æ­ FM97[0*0]",
    "è¥¿å®é³ä¹å¹¿æ­ FM93.1 (Opt-1)[0*0]",
    "é¾å¹¿é³ä¹å¹¿æ­ FM95.8[0*0]",
    "è´µå·çµå°é³ä¹å¹¿æ­ FM91.6[0*0]",
    "éè¥¿é³ä¹å¹¿æ­ FM98.8[0*0]",
]

for name in test_names:
    simplified = NameProcessor.simplify(name)
    print(f"Original: {name}")
    print(f"Simplified: {simplified}")
    print()
