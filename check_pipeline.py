#!/usr/bin/env python3
import sys
sys.path.insert(0, r'C:\tools\IPTV')
with open(r'C:\tools\IPTV\iptv_apex\core\pipeline.py', encoding='utf-8') as f:
    pl = f.read()

for keyword in ['direct_checker', "stats['valid']", 'check_stream', 'def _check', 'check_only']:
    idx = pl.find(keyword)
    if idx >= 0:
        print('[' + keyword[:40] + '] at ' + str(idx) + ':')
        print(repr(pl[idx-5:idx+300]))
        print()
