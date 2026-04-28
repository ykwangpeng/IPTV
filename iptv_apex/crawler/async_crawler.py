#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步爬虫模块
核心：订阅链接拉取时可用代理
"""

import asyncio
import random
import re
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

import httpx

from ..config import Config


class AsyncWebSourceCrawler:
    """异步爬虫：域名质量评分 + HEAD降级GET"""

    PLAYLIST_EXT = ('.m3u', '.m3u8', '.txt', 'php?type=m3u', '/playlist', '?type=m3u')

    URL_PATTERNS = [
        r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt|php\?|\?type=m3u)[^\s<>"\']*',
        r'https?://[^\s<>"\']+/live[^\s<>"\']*',
        r'https?://[^\s<>"\']+/stream[^\s<>"\']*',
        r'https?://[^\s<>"\']+/tv[^\s<>"\']*',
        r'https?://[^\s<>"\']+:\d{4,5}[^\s<>"\']*'
    ]

    def __init__(self):
        self.session = None
        self.all_extracted: Set[str] = set()

    @property
    def SOURCE_SITES(self):
        return Config.PRESET_FILES if Config.PRESET_FILES else Config.WEB_SOURCES

    def _build_proxy(self):
        proxy = getattr(Config, 'PROXY', None)
        return proxy

    async def __aenter__(self):
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30, keepalive_expiry=15.0)
        proxy = self._build_proxy()
        self.session = httpx.AsyncClient(
            timeout=timeout, limits=limits, verify=False,
            follow_redirects=True, proxy=proxy, trust_env=False
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 10.0) -> bool:
        """HEAD 失败自动降级 GET"""
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Range': 'bytes=0-511',
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        }
        try:
            resp = await self.session.head(url, headers=headers, timeout=timeout, follow_redirects=True)
            if resp.status_code in (200, 206, 301, 302, 304):
                return True
            async with self.session.stream('GET', url, headers=headers, timeout=timeout) as resp:
                if resp.status_code in (200, 206) and resp.num_bytes_downloaded >= 16:
                    text = (await resp.aread()).decode('utf-8', errors='ignore')[:200].strip()
                    if text.startswith('#EXTM3U') or 'm3u' in text.lower():
                        return True
            return False
        except Exception:
            return False

    @staticmethod
    def _get_domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    @staticmethod
    def _is_high_quality(url: str) -> int:
        domain = AsyncWebSourceCrawler._get_domain(url)
        if any(bad in domain for bad in Config.PLAYLIST_BLACKLIST_DOMAINS):
            return 0
        if any(good in domain for good in Config.PLAYLIST_WHITELIST):
            return 100
        if "githubusercontent.com" in domain or "github.com" in domain:
            return 70
        return 30

    @staticmethod
    def _is_playlist(url: str) -> bool:
        lower = url.lower()
        auth_params = ('userid=', 'sign=', 'auth_token=', 'token=', 'session=')
        if any(param in lower for param in auth_params):
            return False
        path = urlparse(url).path
        if path.endswith('.m3u8'):
            filename = Path(path).stem
            if filename.isdigit() or len(filename) <= 10:
                return False
        return any(ext in lower for ext in AsyncWebSourceCrawler.PLAYLIST_EXT)

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        """从页面内容中提取直播源"""
        if depth > 1:
            return set()
        try:
            headers = {
                'User-Agent': random.choice(Config.UA_POOL),
                'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            }
            resp = await self.session.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return set()

            text = resp.text
            stripped = text.strip()[:500].lower()
            if (
                len(text) < 50
                or '<!doctype html' in stripped
                or '<html' in stripped
                or '{"code"' in stripped
            ):
                return set()

            all_matches: Set[str] = set()
            for pattern in self.URL_PATTERNS:
                all_matches.update(re.findall(pattern, text, re.IGNORECASE))

            valid_sources: Set[str] = set()
            semaphore = asyncio.Semaphore(30)

            async def validate_and_add(source: str):
                if len(source) < 15 or len(source) > 500:
                    return
                if any(x in source.lower() for x in ['javascript:', 'data:', 'about:', 'void(']):
                    return
                if source in self.all_extracted:
                    return
                async with semaphore:
                    try:
                        if Config.SKIP_WEB_VALIDATE:
                            valid_sources.add(source)
                            self.all_extracted.add(source)
                        elif await self.quick_validate(source, timeout=2.0):
                            valid_sources.add(source)
                            self.all_extracted.add(source)
                    except Exception:
                        pass

            batch_size = 50
            for i in range(0, len(all_matches), batch_size):
                await asyncio.gather(
                    *[validate_and_add(s) for s in list(all_matches)[i:i+batch_size]],
                    return_exceptions=True
                )

            if depth < 1 and valid_sources:
                for src in list(valid_sources)[:10]:
                    if src.endswith(('.m3u', '.m3u8', '.txt')):
                        try:
                            valid_sources.update(await self.extract_sources_from_content(src, depth + 1))
                        except Exception:
                            pass
            return valid_sources
        except Exception:
            return set()

    async def crawl_single_source_with_name(self, url: str, semaphore: asyncio.Semaphore) -> Dict[str, str]:
        """爬取并返回 {子url: 域名} 映射"""
        async with semaphore:
            try:
                parsed_url = urlparse(url)
                base_domain = parsed_url.netloc.split(':')[0]
                if not await self.quick_validate(url, timeout=3.0):
                    return {}
                extracted = await self.extract_sources_from_content(url)
                if not extracted:
                    return {}
                return {sub_url: base_domain for sub_url in extracted}
            except Exception:
                return {}

    async def crawl_all(self) -> Dict[str, str]:
        """爬取所有预设源"""
        print("🔍 启动异步爬虫...")
        semaphore = asyncio.Semaphore(10)
        tasks = [self.crawl_single_source_with_name(url, semaphore) for url in self.SOURCE_SITES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        url_to_name: Dict[str, str] = {}
        for r in results:
            if isinstance(r, dict):
                url_to_name.update(r)
        print(f"✅ 爬虫完成！发现新源 {len(url_to_name)} 个")
        return url_to_name

    async def crawl_all_with_names(self) -> Dict[str, str]:
        """兼容旧接口"""
        return await self.crawl_all()
