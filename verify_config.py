import json
with open(r'C:\tools\IPTV\config.json', encoding='utf-8') as f:
    c = json.load(f)
print(f"web_sources: {len(c['sources']['web_sources'])} sources")
for i, u in enumerate(c['sources']['web_sources']):
    print(f"  {i+1}. {u}")
