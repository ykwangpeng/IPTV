import requests

candidates = [
    ('live.kilvn.com', 'https://live.kilvn.com/iptv.m3u'),
    ('gj8438/TV', 'https://raw.githubusercontent.com/gj8438/TV/main/itvlist.m3u'),
    ('Guovin/iptv-api', 'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt'),
    ('EvilCult/tv.json', 'https://raw.githubusercontent.com/EvilCult/iptv-m3u-maker/master/tv.json'),
]

for name, url in candidates:
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            lines = r.text.count('\n') + 1
            print(f"{name}: OK ({lines} lines)")
            print(f"  Preview: {r.text[:150].replace(chr(10), ' ')[:100]}...")
        else:
            print(f"{name}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{name}: Error - {str(e)[:50]}")
