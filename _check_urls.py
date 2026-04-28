import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 检查这些 URL 是否能播放
import requests

urls = [
    "http://39.165.39.49:85/tsfile/live/1006_1.m3u8?key=txiptv&playlive=0&authid=0",
    "http://39.165.39.49:85/tsfile/live/1088_1.m3u8?key=txiptv&playlive=0&authid=0",
]

session = requests.Session()
session.trust_env = False

for url in urls:
    try:
        resp = session.head(url, timeout=10, allow_redirects=True)
        print(f"URL: {url[:80]}")
        print(f"Status: {resp.status_code}")
        print()
    except Exception as e:
        print(f"URL: {url[:80]}")
        print(f"Error: {e}")
        print()
