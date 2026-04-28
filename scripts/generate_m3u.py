import os
import sys

# 分类中文名 -> M3U group-title 映射
# M3U group-title 使用英文映射
CAT_NAMES = {
    "4K 專區": "4K",
    "港澳台頻": "GDHKTW",
    "影視劇集": "Movies",
    "央視頻道": "CCTV",
    "衛視綜藝": "Variety",
    "體育賽事": "Sports",
    "少兒動漫": "Kids",
    "新聞資訊": "News",
    "音樂頻道": "Music",
    "其他頻道": "Other",
}

def make_group_tag(cat_prefix):
    """Chinese category name -> English group-title"""
    return CAT_NAMES.get(cat_prefix, cat_prefix)

if os.path.exists('live_ok.txt'):
    try:
        with open('live_ok.txt', 'r', encoding='utf-8') as f:
            raw_lines = [l.strip() for l in f if l.strip()]

        if not raw_lines:
            print('live_ok.txt is empty, skip M3U generation')
            sys.exit(0)

        channel_count = 0
        with open('live_ok.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n\n')
            current_group = None
            for line in raw_lines:
                # 新格式：分类行  分类名,#genre#
                if line.endswith(',#genre#'):
                    cat = line[:-9].strip()
                    group = make_group_tag(cat)
                    if group != current_group:
                        f.write(f'#EXTGRP:{group}\n')
                        current_group = group
                # 新格式：频道行  名称,URL
                elif ',' in line and current_group is not None:
                    parts = line.split(',', 1)
                    if len(parts) == 2:
                        name, url = parts
                        f.write(f'#EXTINF:-1 group-title="{current_group}",{name}\n')
                        f.write(f'{url}\n')
                        channel_count += 1
                # 旧格式兜底：  分类|名称,URL
                elif '|' in line:
                    cat_part, rest = line.split('|', 1)
                    if ',' in rest:
                        name, url = rest.split(',', 1)
                        group = make_group_tag(cat_part.strip())
                        if group != current_group:
                            f.write(f'#EXTGRP:{group}\n')
                            current_group = group
                        f.write(f'#EXTINF:-1 group-title="{group}",{name}\n')
                        f.write(f'{url}\n')
                        channel_count += 1

        print(f'M3U done ({channel_count} channels)')
    except Exception as e:
        print(f'M3U generation error: {e}')
        sys.exit(1)
else:
    print('live_ok.txt not found, skip M3U generation')
    sys.exit(0)
