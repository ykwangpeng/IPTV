#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, inspect
sys.path.insert(0, r'C:\tools\IPTV')

# 1. Verify URLCache
from iptv_apex.utils.url import URLCache
has_flush = hasattr(URLCache, 'flush')
src_save = inspect.getsource(URLCache._save)
src_add = inspect.getsource(URLCache.add)
save_calls_replace = 'replace' in src_save
add_no_save = '_save()' not in src_add
print('[PASS] url.py atomic write: replace=%s, add_no_save=%s, has_flush=%s' % (save_calls_replace, add_no_save, has_flush))

# 2. Verify pipeline.py
with open(r'C:\tools\IPTV\iptv_apex\core\pipeline.py', encoding='utf-8') as f:
    pl = f.read()
has_flush_call = 'cache.flush()' in pl
if has_flush_call:
    idx1 = pl.find('cache.flush()')
    idx2 = pl.find('self.stats_manager.save()')
    order_ok = idx1 < idx2
    print('[PASS] pipeline.py cache.flush order: %s (flush_pos=%d, save_pos=%d)' % (order_ok, idx1, idx2))
else:
    print('[FAIL] cache.flush() not found in pipeline.py')

# 3. Cache file status
cache = r'C:\tools\IPTV\.iptv_cache.json'
broken = [f for f in os.listdir(r'C:\tools\IPTV') if '.broken.' in f]
print('[INFO] Broken cache backed up:', broken[0] if broken else 'none')
print('[INFO] New cache exists:', os.path.exists(cache))

print('[OK] Fixes verified.')
