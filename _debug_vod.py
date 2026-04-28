import sys
sys.path.insert(0, 'C:\\tools\\IPTV')

from iptv_apex.config import Config
from iptv_apex.utils.url import URLCleaner

# 加载配置
Config.load_from_file()

print(f"VOD_DOMAINS size: {len(Config.VOD_DOMAINS)}")
print(f"VOD_DOMAINS: {list(Config.VOD_DOMAINS)[:10]}")

# 测试一些 URL
test_urls = [
    "http://ls.qingting.fm/live/1929.m3u8",
    "https://txmov2.a.kwimgs.com/bs3/video-hls/5203065042375807425_hlsb.m3u8",
    "http://ddns.xryo.cn:8888/udp/239.111.205.67:5140",
]

for url in test_urls:
    result = URLCleaner.is_vod_domain(url)
    print(f"URL: {url}")
    print(f"  is_vod_domain: {result}")
    print(f"  netloc: {URLCleaner._get_hostname(url)}")
