#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步网络源拉取器
"""

import random
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

    def fetch(self, url: str, proxy: Optional[str] = None, timeout: int = 15) -> List[str]:
        """拉取并解析源列表"""
        try:
            proxies = {'http': proxy, 'https': proxy} if proxy else None
            resp = self.session.get(url, proxies=proxes, timeout=timeout, verify=False)
            resp.raise_for_status()
            
            content = resp.text
            lines = []
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ',' in line:
                    lines.append(line)
                elif line.startswith(('http://', 'https://')):
                    # M3U格式：提取URL，频道名用域名
                    domain = urlparse(line).netloc
                    lines.append(f"{domain},{line}")
            return lines
        except Exception:
            return []
