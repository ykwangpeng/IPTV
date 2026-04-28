#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URL 工具模块：缓存、清理、指纹
"""

import hashlib
import ipaddress
import json
import time
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from ..config import Config


class URLCache:
    """轻量级 URL 去重缓存"""

    def __init__(self, cache_file: Path, ttl_hours: int = 24):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_hours * 3600
        self.cache: Dict[str, float] = {}
        self._load()
        self._cleanup_expired()

    def _load(self):
        if not Config.ENABLE_CACHE:
            return
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
        except Exception:
            self.cache = {}

    def _save(self):
        if not Config.ENABLE_CACHE:
            return
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _cleanup_expired(self):
        now = time.time()
        expired = [k for k, v in self.cache.items() if now - v > self.ttl_seconds]
        for k in expired:
            del self.cache[k]
        if expired:
            self._save()

    def is_cached(self, fingerprint: str) -> bool:
        if not Config.ENABLE_CACHE:
            return False
        if fingerprint in self.cache:
            if time.time() - self.cache[fingerprint] <= self.ttl_seconds:
                return True
            del self.cache[fingerprint]
            self._save()
        return False

    def add(self, fingerprint: str):
        if not Config.ENABLE_CACHE:
            return
        self.cache[fingerprint] = time.time()
        self._save()


class URLCleaner:
    """URL 清理工具"""

    @staticmethod
    def get_fingerprint(url: str) -> str:
        """URL 指纹（去参数）"""
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            path = parsed.path
            return hashlib.md5(f"{netloc}{path}".encode()).hexdigest()[:16]
        except Exception:
            return hashlib.md5(url.encode()).hexdigest()[:16]

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        """过滤内网 IP"""
        if not Config.FILTER_PRIVATE_IP:
            return False
        try:
            host = urlparse(url).hostname
            if not host:
                return False
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            return False

    @staticmethod
    def is_vod_domain(url: str) -> bool:
        """检查是否为点播域名"""
        if not Config.VOD_DOMAINS:
            return False
        try:
            netloc = urlparse(url).netloc.lower()
            return any(vod in netloc for vod in Config.VOD_DOMAINS)
        except Exception:
            return False

    @staticmethod
    def _get_hostname(url: str) -> str:
        """提取主机名"""
        try:
            return urlparse(url).hostname or ''
        except Exception:
            return ''
