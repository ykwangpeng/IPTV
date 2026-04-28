#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直播流检测模块
核心：频道测活时不能用代理
"""

import random
import time
from typing import Dict, Optional

import requests

from ..config import Config


class StreamChecker:
    """直播流检测器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18'
        })

    def check(self, line: str, proxy: Optional[str] = None) -> Optional[Dict]:
        """检测单条直播源，返回结果字典或 None"""
        try:
            name, url = line.split(',', 1)
            name = name.strip()
            url = url.strip()
        except ValueError:
            return None

        if not url.startswith(('http://', 'https://', 'udp://', 'rtp://', 'srt://')):
            return None

        # 判断境内外
        is_overseas = self._is_overseas_name(name)
        timeout = Config.TIMEOUT_OVERSEAS if is_overseas else Config.TIMEOUT_CN

        # 检测逻辑
        result = self._check_with_http(url, timeout, proxy)
        if not result:
            return None

        result['name'] = name
        result['url'] = url
        result['overseas'] = is_overseas
        return result

    @staticmethod
    def _is_overseas_name(name: str) -> bool:
        name_upper = name.upper()
        return any(kw.upper() in name_upper for kw in Config.OVERSEAS_KEYWORDS)

    def _check_with_http(self, url: str, timeout: int, proxy: Optional[str] = None) -> Optional[Dict]:
        """HTTP 流检测，支持 IPv6 和重定向"""
        try:
            headers = {
                'User-Agent': random.choice(Config.UA_POOL),
                'Range': 'bytes=0-32767',
                'Accept': '*/*',
                'Connection': 'keep-alive',
            }
            proxies = {'http': proxy, 'https': proxy} if proxy else None

            resp = self.session.get(url, headers=headers, timeout=timeout,
                                   stream=True, verify=False, proxies=proxies,
                                   allow_redirects=True)
            # 301/302 跟随后检查最终状态
            if resp.status_code not in (200, 206):
                return None

            content = b''
            for chunk in resp.iter_content(chunk_size=8192):
                content += chunk
                if len(content) >= 32768:
                    break

            if len(content) < 512:
                return None

            # 检查内容类型
            content_type = resp.headers.get('Content-Type', '').lower()
            if 'html' in content_type and not content.startswith(b'#EXTM3U'):
                return None

            # 验证是否为媒体流
            if self._is_media_content(content):
                quality = self._estimate_quality(content, resp.headers)
                return {
                    'quality': quality,
                    'delay': 0.1,
                    'speed': 0.0
                }
            return None
        except Exception:
            return None

    @staticmethod
    def _is_media_content(content: bytes) -> bool:
        """判断内容是否为媒体流"""
        if len(content) < 16:
            return False
        # M3U8
        if content.startswith(b'#EXTM3U'):
            return True
        # TS
        if content[:1] == b'\x47' or content.find(b'\x47') < 188:
            return True
        # FLV
        if content[:3] == b'FLV':
            return True
        # MP4
        if content[4:8] == b'ftyp':
            return True
        return False

    @staticmethod
    def _estimate_quality(content: bytes, headers: dict) -> int:
        """估算质量分数"""
        quality = 50
        content_length = headers.get('Content-Length')
        if content_length:
            try:
                size = int(content_length)
                if size > 1000000:
                    quality += 20
                elif size > 500000:
                    quality += 10
            except ValueError:
                pass
        return min(quality, 100)

    def check_speed(self, url: str, proxy: Optional[str] = None) -> float:
        """检测下载速度 (MB/s)"""
        try:
            headers = {'User-Agent': random.choice(Config.UA_POOL)}
            proxies = {'http': proxy, 'https': proxy} if proxy else None
            start = time.time()
            resp = self.session.get(url, headers=headers, stream=True,
                                   verify=False, proxies=proxies, timeout=10)
            if resp.status_code not in (200, 206):
                return 0.0
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded >= Config.SPEED_CHECK_BYTES:
                    break
            elapsed = time.time() - start
            return (downloaded / 1024 / 1024) / elapsed if elapsed > 0 else 0.0
        except Exception:
            return 0.0
