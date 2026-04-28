#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U 解析器
"""

import re
from typing import List, Tuple


class M3UParser:
    """M3U/M3U8 播放列表解析"""

    @staticmethod
    def parse(content: str) -> List[Tuple[str, str]]:
        """解析 M3U 内容，返回 [(频道名, URL), ...]"""
        results = []
        lines = content.strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                # 提取频道名
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                if name_match:
                    name = name_match.group(1)
                else:
                    # 从逗号后提取
                    if ',' in line:
                        name = line.split(',', 1)[1].strip()
                    else:
                        name = '未知频道'
                # 下一行是 URL
                if i + 1 < len(lines):
                    url = lines[i + 1].strip()
                    if url and not url.startswith('#'):
                        results.append((name, url))
                    i += 2
                    continue
            elif line and not line.startswith('#') and ',' in line:
                # 简单 name,url 格式
                name, url = line.split(',', 1)
                results.append((name.strip(), url.strip()))
            i += 1
        return results

    @staticmethod
    def parse_txt(content: str) -> List[Tuple[str, str]]:
        """解析 txt 格式（name,url）"""
        results = []
        for line in content.strip().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ',' in line:
                name, url = line.split(',', 1)
                results.append((name.strip(), url.strip()))
        return results
