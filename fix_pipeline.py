#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 pipeline.py 在 stats_manager.save() 前调用 cache.flush()"""
import re

path = r'C:\tools\IPTV\iptv_apex\core\pipeline.py'
with open(path, encoding='utf-8') as f:
    content = f.read()

# Pattern: stats_manager.save() preceded by various update() calls
# We want to add cache.flush() BEFORE stats_manager.save()
old = (
    "            self.stats_manager.update('failed', self.stats['failed'])\n"
    "            self.stats_manager.update('filtered', self.stats['filtered_by_quality'])\n"
    "            self.stats_manager.update('written', _total_written)\n"
    "            self.stats_manager.update('duration_seconds', duration)\n"
    "            self.stats_manager.save()"
)
new = (
    "            self.stats_manager.update('failed', self.stats['failed'])\n"
    "            self.stats_manager.update('filtered', self.stats['filtered_by_quality'])\n"
    "            self.stats_manager.update('written', _total_written)\n"
    "            self.stats_manager.update('duration_seconds', duration)\n"
    "            self.cache.flush()  # 一次性原子写入缓存\n"
    "            self.stats_manager.save()"
)

if old not in content:
    print("ERROR: Pattern not found in pipeline.py")
    # Try a looser search
    idx = content.find("self.stats_manager.save()")
    if idx >= 0:
        print(f"Found stats_manager.save() at position {idx}")
        print("Context:")
        print(repr(content[idx-200:idx+50]))
    else:
        print("stats_manager.save() not found at all")
else:
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK - cache.flush() added before stats_manager.save()")
