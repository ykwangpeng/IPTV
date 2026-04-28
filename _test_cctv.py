import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, 'C:\\tools\\IPTV')

from iptv_apex.config import Config
from iptv_apex.utils.name import NameProcessor

# 加载配置
Config.load_from_file()
Config.init_compiled_rules()

# 测试 CCTV 分类
test_names = [
    "CCTV1",
    "CCTV2",
    "CCTV6",
    "CCTV13",
    "CCTV-1",
    "CCTV-13",
    "CCTV1综合",
    "CCTV13新闻",
]

for name in test_names:
    category = NameProcessor.classify(name)
    print(f"{name} -> {category}")
