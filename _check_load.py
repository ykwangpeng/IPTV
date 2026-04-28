import os
import sys
sys.path.insert(0, 'C:\\tools\\IPTV')

from iptv_apex.config import Config

print("Before load:")
print(f"VOD_DOMAINS size: {len(Config.VOD_DOMAINS)}")
print(f"VOD_DOMAINS: {list(Config.VOD_DOMAINS)[:5]}...")

Config.load_from_file()

print("\nAfter load:")
print(f"VOD_DOMAINS size: {len(Config.VOD_DOMAINS)}")
print(f"VOD_DOMAINS: {list(Config.VOD_DOMAINS)[:5]}...")
