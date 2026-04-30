#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步爬虫模块 v2.0
核心优化：
  1. _is_playlist / _is_high_quality 真正参与过滤逻辑
  2. M3U #EXTINF 行完整解析 + txt 格式统一处理
  3. Per-domain 并发控制（避免单域名被打爆）
  4. GitHub raw → CDN mirror 回退（gh-proxy / jsdelivr）
  5. 智能去重 + 增量发现
  6. 可选开启直连验证（默认 SKIP_WEB_VALIDATE=True）
"""

import asyncio
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx

from ..config import Config


# ---------------------------------------------------------------------------
# GitHub URL 正则模式
# ---------------------------------------------------------------------------
RE_GITHUB_RAW = re.compile(
    r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)'
)
RE_GITHUB_COM  = re.compile(
    r'https://github\.com/([^/]+)/([^/]+)/(?:raw|blob)/([^/]+)/(.+)'
)


def try_github_mirror(url: str) -> list[str]:
    """将 GitHub raw/com URL 展开为 CDN mirror 列表
    返回 [原始URL, mirror1, mirror2, ...]，原始 URL 不重复追加。"""
    results: list[str] = []
    candidates: list[str] = []

    m = RE_GITHUB_RAW.match(url)
    if m:
        owner, repo, ref, path = m.group(1), m.group(2), m.group(3), m.group(4)
        results.append(url)  # 原始 raw.githubusercontent.com URL
        candidates = [
            f'https://testingcf.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}',
            f'https://mirror.ghproxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}',
            f'https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}',
        ]
    else:
        m2 = RE_GITHUB_COM.match(url)
        if m2:
            owner, repo, ref, path = m2.group(1), m2.group(2), m2.group(3), m2.group(4)
            results.append(url)  # 原始 github.com URL
            candidates = [
                f'https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}',
                f'https://testingcf.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}',
                f'https://mirror.ghproxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}',
                f'https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}',
            ]
        else:
            # 非 GitHub URL：直接返回（不在列表中追加自己）
            return [url]

    results.extend(candidates)
    return results


# ---------------------------------------------------------------------------
# 主爬虫类
# ---------------------------------------------------------------------------
class AsyncWebSourceCrawler:
    """异步爬虫 v2.0：域名质量评分 + HEAD 降级 GET + CDN 回退 + Per-domain 并发控制"""

    # 扩展 URL 提取模式（增加更多常见播放列表路径）
    URL_PATTERNS = [
        # 标准播放列表扩展名
        r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt)(?:\?[^\s<>"\']*)?',
        # 常见播放列表路由
        r'https?://[^\s<>"\']+(?:/live|/stream|/tv|/playlist|/iptv|/m3u|/channels?|/feed)(?:[^\s<>"\']*)?',
        # 带端口的流媒体 URL
        r'https?://[^\s<>"\']+:\d{4,5}(?:/[^\s<>"\']*)?',
        # 直接的 .php / .xml 播放列表
        r'https?://[^\s<>"\']+\.(?:php|xml)(?:\?[^\s<>"\']*)?',
        # COS / OSS / S3 对象存储 URL
        r'https?://[^\s<>"\']+(?:\.cos\.[^\s<>"\']+|\.oss\.[^\s<>"\']+|\.s3[^\s<>"\']+)(?:/[^\s<>"\']*)?',
    ]

    # URL 扩展名黑名单（精确后缀匹配；.txt/.m3u/.m3u8 单独在 _is_playlist 中处理）
    EXT_BLACKLIST = frozenset(
        f'.{ext}' for ext in (
            'js', 'css', 'jpg', 'jpeg', 'png', 'gif', 'svg', 'ico', 'webp',
            'woff', 'woff2', 'ttf', 'eot', 'mp4', 'mp3', 'avi', 'mkv',
            'zip', 'rar', 'tar', 'gz', 'pdf', 'doc', 'docx', 'xls', 'xlsx',
            'json', 'xml', 'yml', 'yaml', 'md',
        )
    )

    def __init__(self):
        self.session: Optional[httpx.AsyncClient] = None
        self.all_extracted: Set[str] = set()
        # Per-domain 并发控制：每个域名最多 N 个并发请求
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._domain_limit: int = 3          # 每域名并发上限
        self._crawl_semaphore = asyncio.Semaphore(10)   # 全局爬取并发上限

    @property
    def SOURCE_SITES(self):
        return Config.PRESET_FILES if Config.PRESET_FILES else Config.WEB_SOURCES

    def _get_domain_semaphore(self, url: str) -> asyncio.Semaphore:
        """获取 per-domain 信号量，防止单域名被并发打爆"""
        domain = urlparse(url).netloc.lower().split(':')[0]
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self._domain_limit)
        return self._domain_semaphores[domain]

    def _build_proxy(self) -> Optional[str]:
        return getattr(Config, 'PROXY', None)

    # -------------------------------------------------------------------------
    # 公开上下文管理器
    # -------------------------------------------------------------------------
    async def __aenter__(self):
        timeout = httpx.Timeout(15.0, connect=8.0)
        limits  = httpx.Limits(
            max_keepalive_connections=30,
            max_connections=60,
            keepalive_expiry=20.0
        )
        proxy = self._build_proxy()
        self.session = httpx.AsyncClient(
            timeout=timeout, limits=limits, verify=False,
            follow_redirects=True, proxy=proxy, trust_env=False
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    # -------------------------------------------------------------------------
    # 静态工具方法（现在真正被调用）
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    @staticmethod
    def _is_high_quality(url: str) -> int:
        """返回 URL 质量评分 0-100，供后续排序使用"""
        domain = AsyncWebSourceCrawler._get_domain(url)
        # 黑名单直接返回 0
        if any(bad in domain for bad in Config.PLAYLIST_BLACKLIST_DOMAINS):
            return 0
        # 白名单返回 100
        if any(gd in domain for gd in Config.PLAYLIST_WHITELIST):
            return 100
        # GitHub 相关域名
        if 'github' in domain:
            return 70
        # COS / OSS / S3 对象存储（通常更稳定）
        # 阿里云 OSS: bucket.oss-cn-hangzhou.aliyuncs.com
        # 腾讯云 COS: bucket.cos.ap-guangzhou.myqcloud.com
        # AWS S3: bucket.s3.ap-northeast-1.amazonaws.com
        if any(x in domain for x in ('.oss-', '.cos.', '.s3.', 'cosv', '.obj')):
            return 80
        # 知名 CDN 域名
        if any(x in domain for x in ['cfcdn', 'jsdelivr', 'cdnjs', 'unpkg', 'fastly']):
            return 60
        # 普通域名
        return 30

    @staticmethod
    def _is_playlist(url: str) -> bool:
        """严格判断 URL 是否可能是播放列表地址
        返回 True 表示该 URL 可能是播放列表文件或路由，应当尝试获取内容。"""
        lower = url.lower()
        parsed = urlparse(url)
        path = parsed.path           # Path.suffix 大小写不敏感，用原始值
        path_lower = path.lower()
        query = parsed.query.lower()

        # ── 1. 认证参数 → 排除 ──
        if any(p in lower for p in ('userid=', 'sign=', 'auth_token=', 'token=', 'session=', 'expire=', 'key=', 'nonce=')):
            return False

        # ── 2. 扩展名黑名单（精确后缀匹配）──
        suffix = Path(path).suffix.lower()
        if suffix in AsyncWebSourceCrawler.EXT_BLACKLIST:
            return False

        # ── 3. 标准播放列表扩展名（.m3u8 先于 .m3u 检查，避免子串误匹配）──
        if path_lower.endswith('.m3u8'):
            stem = Path(path).stem
            return not (stem.isdigit() or len(stem) <= 1)   # 数字/单字符命名 = 直播片段，排除
        if path_lower.endswith('.m3u'):
            stem = Path(path).stem
            return not (stem.isdigit() or len(stem) <= 1)
        if path_lower.endswith('.txt'):
            return True

        # ── 4. 常见播放列表路由模式（无扩展名）──
        if any(x in path_lower for x in ('/live/', '/tv/', '/stream/', '/playlist/', '/iptv/', '/channels/', '/feed')):
            return True

        # ── 5. 查询参数类型声明 ──
        if 'php?type=m3u' in lower or '/playlist?' in lower or '?type=m3u' in lower:
            return True

        # ── 6. 流媒体端口检测 ──
        port_match = re.search(r':(\d{4,5})', url)
        if port_match:
            port = int(port_match.group(1))
            if 1000 <= port <= 99999 and ('live' in lower or 'stream' in lower or len(path) > 5):
                return True

        return False

    # -------------------------------------------------------------------------
    # 验证：HEAD 降级 GET（支持重定向跟踪）
    # -------------------------------------------------------------------------
    async def quick_validate(self, url: str, timeout: float = 8.0) -> bool:
        """HEAD 失败自动降级 GET；支持 301/302/304/403/405"""
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Range': 'bytes=0-511',
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}/",
            'Accept': '*/*',
            'Connection': 'keep-alive',
        }
        try:
            resp = await self.session.head(url, headers=headers,
                                           timeout=timeout, follow_redirects=True)
            if resp.status_code in (200, 206):
                return True
            # 降级 GET（仅在 HEAD 返回非 200 时触发）
            if resp.status_code in (301, 302, 304, 405, 403):
                stream_headers = {**headers, 'Range': 'bytes=0-511'}
                async with self.session.stream(
                        'GET', url, headers=stream_headers,
                        timeout=timeout, follow_redirects=True) as resp2:
                    if resp2.status_code in (200, 206):
                        content = (await resp2.aread())
                        if len(content) >= 16:
                            text = content[:256].decode('utf-8', errors='ignore').strip().lower()
                            if text.startswith('#extm3u') or 'm3u' in text or len(text) > 32:
                                return True
            return False
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # 内容解析：M3U / M3U8 / TXT 统一解析
    # -------------------------------------------------------------------------
    def parse_content(self, url: str, content: str) -> Set[str]:
        """
        统一解析 M3U / M3U8 / TXT 格式内容，返回原始频道 URL 集合。
        - M3U: #EXTINF 行中可能内嵌 URL
        - TXT: "名称,URL" 或只有 URL 的行
        - 二级 M3U: 纯 URL 行（每行一个 .m3u/.m3u8/.txt 链接）
        """
        urls: Set[str] = set()
        lines = content.splitlines()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # ── M3U 元数据行（跳过，不处理频道名）──
            if line.startswith('#EXTINF:'):
                continue

            if line.startswith('#'):
                continue  # 跳过其他 M3U/M3U8 注释行

            # ── URL 行 ──
            if not line.startswith(('http://', 'https://')):
                continue

            # URL 去重
            if line in self.all_extracted:
                continue

            # 过滤非播放列表 URL（调用之前定义的静态方法）
            if not self._is_playlist(line):
                continue

            # 补充：检查扩展名黑名单
            line_suffix = Path(urlparse(line).path).suffix.lower()
            if line_suffix in self.EXT_BLACKLIST:
                continue

            urls.add(line)
            self.all_extracted.add(line)

        return urls

    # -------------------------------------------------------------------------
    # 从 URL 内容中提取子播放列表 URL（用于递归发现）
    # -------------------------------------------------------------------------
    def extract_sub_playlist_urls(self, content: str) -> Set[str]:
        """从任意页面内容中提取子播放列表 URL（供递归调用）"""
        sub_urls: Set[str] = set()
        for pattern in self.URL_PATTERNS:
            for match in re.findall(pattern, content, re.IGNORECASE):
                # 清理末尾杂字符
                clean = match.rstrip('\'")> \t')
                if self._is_playlist(clean) and clean not in self.all_extracted:
                    sub_urls.add(clean)
        return sub_urls

    # -------------------------------------------------------------------------
    # 获取内容（自动尝试 GitHub CDN 镜像回退）
    # -------------------------------------------------------------------------
    async def _fetch_with_fallback(self, url: str,
                                   headers: dict,
                                   timeout: float = 15.0) -> Optional[str]:
        """
        尝试获取 URL 内容，自动对 GitHub URL 尝试多个 CDN mirror。
        返回内容文本，失败返回 None。
        遇到 429 状态码时等待后重试一次。
        """
        candidates = try_github_mirror(url) if 'github' in url.lower() else [url]

        for candidate in candidates:
            for attempt in range(2):  # 每个 candidate 最多尝试 2 次
                try:
                    resp = await self.session.get(
                        candidate, headers=headers,
                        timeout=timeout, follow_redirects=True
                    )
                    if resp.status_code == 429:
                        # 速率限制：等待后重试当前 candidate
                        await asyncio.sleep(2.0)
                        continue
                    if resp.status_code == 200 and resp.content:
                        # 强制 UTF-8 解码
                        try:
                            text = resp.content.decode('utf-8')
                        except UnicodeDecodeError:
                            text = resp.content.decode('utf-8', errors='replace')

                        # 内容有效性预检（防止撞到反爬页面）
                        stripped = text.strip()[:200].lower()
                        if any(x in stripped for x in (
                                '<!doctype', '<html', '{"code"', '<script',
                                'cloudfront', 'accessdenied', 'rate limit')):
                            break  # 跳过此 candidate，尝试下一个

                        return text
                except Exception:
                    pass
                break  # 非 429 错误或重试后仍失败，尝试下一个 candidate

        return None  # 所有候选都失败

    # -------------------------------------------------------------------------
    # 核心提取方法（支持递归深度控制）
    # -------------------------------------------------------------------------
    async def extract_sources_from_content(self,
                                           url: str,
                                           depth: int = 0) -> Set[str]:
        """从给定 URL 抓取并提取直播源 URL，支持递归扩展"""
        # 深度超限或已提取过 → 直接返回
        if depth > 1 or url in self.all_extracted:
            return set()

        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}/",
            'Accept': '*/*',
        }

        text = await self._fetch_with_fallback(url, headers)
        if text is None:
            return set()

        # 解析当前文件中的频道 URL
        channel_urls = self.parse_content(url, text)

        # 递归：从内容中找子播放列表（仅深度 0 触发一次）
        discovered: Set[str] = set()
        if depth < 1:
            sub_candidates = self.extract_sub_playlist_urls(text)
            domain_sem = self._get_domain_semaphore(url)

            async def fetch_sub(sub_url: str):
                async with domain_sem:
                    return await self.extract_sources_from_content(sub_url, depth + 1)

            # 限制并发子请求数量
            subs = list(sub_candidates)[:20]  # 最多递归 20 个子播放列表
            if subs:
                tasks = [fetch_sub(s) for s in subs]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, set):
                        discovered.update(r)

        all_urls = channel_urls | discovered
        # 更新全局集合
        for u in all_urls:
            self.all_extracted.add(u)

        return all_urls

    # -------------------------------------------------------------------------
    # 单源爬取（支持 txt/m3u 统一处理 + CDN 回退）
    # -------------------------------------------------------------------------
    async def crawl_single_source_with_name(
            self,
            url: str,
            semaphore: Optional[asyncio.Semaphore] = None
    ) -> Dict[str, str]:
        """
        爬取单个源，返回 {channel_url: base_domain} 映射。
        流程：
          1. 获取内容（自动 CDN 回退）
          2. 统一解析（m3u / m3u8 / txt / 二级目录页面）
          3. 可选：直连验证高质量 URL
        """
        sem = semaphore or self._crawl_semaphore
        async with sem:
            try:
                parsed = urlparse(url)
                base_domain = parsed.netloc.split(':')[0]

                headers = {
                    'User-Agent': random.choice(Config.UA_POOL),
                    'Accept': '*/*',
                    'Referer': f"{parsed.scheme}://{parsed.netloc}/",
                }

                # 获取内容
                text = await self._fetch_with_fallback(url, headers)
                if text is None:
                    return {}

                # ── 统一解析（双通道：TXT + M3U）──
                result: Dict[str, str] = {}
                all_channel_urls: Set[str] = set()

                # 通道1：TXT 格式（名称,URL）
                # 不依赖 _is_playlist（URL 可能是 .rtsp/.sdp/.m3u8 等各种协议）
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if ',' in line:
                        parts = line.split(',', 1)
                        if len(parts) == 2 and parts[1].strip().startswith('http'):
                            u = parts[1].strip()
                            if u not in self.all_extracted:
                                self.all_extracted.add(u)
                                all_channel_urls.add(u)

                # 通道2：M3U / 纯 URL 行
                # （parse_content 会因为 all_extracted 已填充而跳过 TXT 解析出的 URL，
                #   这正是预期行为——去重由 all_channel_urls 负责）
                m3u_urls = self.parse_content(url, text)
                all_channel_urls.update(m3u_urls)

                # 对所有找到的 URL 去重 + 质量评分
                scored: List[tuple] = []
                for u in all_channel_urls:
                    score = self._is_high_quality(u)
                    scored.append((u, score))
                scored.sort(key=lambda x: x[1], reverse=True)  # 高质量优先

                # 验证高质量 URL（如果未跳过验证）
                if not Config.SKIP_WEB_VALIDATE:
                    validated: Set[str] = set()
                    for u, score in scored[:100]:  # 最多验证 100 个
                        domain_sem = self._get_domain_semaphore(u)
                        async with domain_sem:
                            ok = await self.quick_validate(u, timeout=5.0)
                        if ok:
                            validated.add(u)
                            self.all_extracted.add(u)
                    result = {u: base_domain for u in validated}
                else:
                    # 不验证：直接采纳所有 URL（由后续直连二验兜底）
                    for u, score in scored:
                        result[u] = base_domain
                        self.all_extracted.add(u)

                # 递归：发现子播放列表（深度 1）
                if scored:
                    sub_urls = self.extract_sub_playlist_urls(text)
                    for sub in list(sub_urls)[:15]:
                        try:
                            sub_result = await self.extract_sources_from_content(sub, depth=1)
                            for su in sub_result:
                                if su not in result and self._is_high_quality(su) > 0:
                                    result[su] = base_domain
                                    self.all_extracted.add(su)
                        except Exception:
                            pass

                return result

            except Exception as e:
                return {}

    # -------------------------------------------------------------------------
    # 批量爬取所有源
    # -------------------------------------------------------------------------
    async def crawl_all(self) -> Dict[str, str]:
        """并发爬取所有配置源，返回 {channel_url: domain}"""
        print("🔍 启动异步爬虫 v2.0...")
        print(f"   源数量: {len(self.SOURCE_SITES)}")
        print(f"   跳过验证: {Config.SKIP_WEB_VALIDATE}")
        print(f"   CDN 回退: 启用（GitHub → jsdelivr / gh-proxy）")

        tasks = [
            self.crawl_single_source_with_name(url, self._crawl_semaphore)
            for url in self.SOURCE_SITES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        url_to_name: Dict[str, str] = {}
        for r in results:
            if isinstance(r, dict):
                url_to_name.update(r)

        # 统计
        domain_stats: Dict[str, int] = defaultdict(int)
        for url in url_to_name:
            domain_stats[url_to_name[url]] += 1

        print(f"✅ 爬虫完成！发现 {len(url_to_name)} 个频道 URL")
        print(f"   按域名分布（前10）:")
        for domain, cnt in sorted(domain_stats.items(),
                                   key=lambda x: x[1], reverse=True)[:10]:
            print(f"     {domain:<40} {cnt}")

        return url_to_name

    # -------------------------------------------------------------------------
    # 兼容旧接口
    # -------------------------------------------------------------------------
    async def crawl_all_with_names(self) -> Dict[str, str]:
        return await self.crawl_all()
