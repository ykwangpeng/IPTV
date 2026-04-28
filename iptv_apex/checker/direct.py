#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直连二验模块
核心：过滤海外域名/GFW封禁/token过期源
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import requests

from ..config import Config


class DirectChecker:
    """直连可用性验证"""

    # 已知可靠CDN域名关键词
    KNOWN_DIRECT = {
        'live.264788', 'goodiptv', '163189', 'jdshipin',
        'tencentplay', 'bp-resource', 'bestv', 'amucn',
        'xryo', 'migu', 'dsj', 'ottiptv', 'iill',
        'aktv', '061833', '888', 'ott.mobai', 'mobai',
        'cdn8.', 'cdn6.', 'cdn12.', 'cdn.', 'cos.',
        'tencent.', 'aliyun', 'alicdn', 'ali-cdn',
        'speedws',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18'
        })

    def is_known_direct(self, url: str) -> bool:
        """检查是否为已知可靠CDN"""
        try:
            netloc = url.split('://', 1)[-1].split('?')[0].split('/')[0].lower()
            for k in self.KNOWN_DIRECT:
                if netloc == k or netloc.endswith('.' + k):
                    return True
        except Exception:
            pass
        return False

    def check_one(self, channel: Dict) -> bool:
        """单条直连检测（不用代理）"""
        url = channel.get('url', '')
        if not url:
            return False

        # UDP/RTP/SRT 直接通过
        if url.startswith(('udp://', 'rtp://', 'srt://')):
            return True

        # 已知CDN直接通过
        if self.is_known_direct(url):
            return True

        # 直连检测（不用代理）
        no_proxy = {'http': None, 'https': None}
        try:
            r = self.session.head(url, timeout=4, verify=False,
                                 allow_redirects=True, proxies=no_proxy)
            if r.status_code in (200, 206):
                return True
            if r.status_code >= 400:
                r2 = self.session.get(url, timeout=4, verify=False,
                                      stream=True, proxies=no_proxy,
                                      headers={'Range': 'bytes=0-511'})
                if r2.status_code in (200, 206):
                    content = r2.content[:200].decode('utf-8', errors='ignore')
                    if '#extm3u' in content.lower() or 'stream' in content.lower():
                        return True
                return False
            return r.status_code < 500
        except Exception:
            return False

    def filter_channels(self, cat_map: Dict[str, List[Dict]], max_workers: int = 80) -> Dict[str, List[Dict]]:
        """批量直连二验，返回过滤后的 cat_map"""
        # 收集所有频道
        all_channels = []
        for cat, channels in cat_map.items():
            for ch in channels:
                all_channels.append((cat, ch))

        # 分离已知直通和待检测
        to_test = []
        for cat, ch in all_channels:
            url = ch.get('url', '')
            if url.startswith(('udp://', 'rtp://', 'srt://')):
                ch['_direct_ok'] = True
            elif self.is_known_direct(url):
                ch['_direct_ok'] = True
            else:
                to_test.append((cat, ch))

        total = len(all_channels)
        print(f'直连二验: 总计 {total} 个 | 直通 {total - len(to_test)} 个 | 待检测 {len(to_test)} 个')

        # 并发检测
        if to_test:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(self.check_one, ch): (cat, ch) for cat, ch in to_test}
                for fut in as_completed(futures):
                    cat, ch = futures[fut]
                    ch['_direct_ok'] = fut.result()

        # 重建 cat_map
        removed = 0
        result = {}
        for cat in cat_map:
            still = [c for c in cat_map[cat] if c.get('_direct_ok', True)]
            removed += len(cat_map[cat]) - len(still)
            if still:
                result[cat] = still

        valid = sum(len(v) for v in result.values())
        print(f'直连二验: 过滤 {removed} 个无效源，剩余 {valid} 个有效')
        return result
