#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步网络源拉取器
"""

import random
import re
from typing import List, Optional

import requests
from urllib.parse import urlparse

from ..config import Config


class WebSourceFetcher:
    """同步拉取网络源"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(Config.UA_POOL)
        })
        self.session.trust_env = False

    def fetch(self, url: str, proxy: Optional[str] = None, timeout: int = 15) -> List[str]:
        """拉取并解析源列表，支持 txt/m3u/m3u8 格式"""
        try:
            proxies = {'http': proxy, 'https': proxy} if proxy else None
            resp = self.session.get(url, proxies=proxies, timeout=timeout, verify=False,
                                    headers={'Accept': '*/*', 'User-Agent': random.choice(Config.UA_POOL)})
            resp.raise_for_status()

            # 强制使用 UTF-8 解码，避免编码错误
            if resp.encoding and resp.encoding.lower() != 'utf-8':
                content = resp.content.decode('utf-8', errors='replace')
            else:
                content = resp.text
            lines = []
            current_name = None

            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                # M3U 格式解析
                if line.startswith('#EXTINF:'):
                    # 提取频道名
                    if 'group-title=' in line:
                        # 从 group-title 和频道名提取
                        match = re.search(r',([^,]+)$', line)
                        if match:
                            current_name = match.group(1).strip()
                    else:
                        match = re.search(r',([^,]+)$', line)
                        if match:
                            current_name = match.group(1).strip()
                elif line.startswith('#'):
                    continue
                elif line.startswith(('http://', 'https://')):
                    # M3U URL 行
                    name = current_name or urlparse(line).netloc
                    lines.append(f"{name},{line}")
                    current_name = None
                elif ',' in line and not line.endswith(',#genre#'):
                    # TXT 格式: 名称,URL
                    parts = line.split(',', 1)
                    if len(parts) == 2 and parts[1].strip().startswith('http'):
                        lines.append(line)

            return lines
        except Exception:
            return []
