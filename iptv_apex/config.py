#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
支持从 config.json 加载配置，保留代码级默认值
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Any


class Config:
    """配置中心：代码默认值 + config.json 覆盖"""

    BASE_DIR = Path(__file__).parent.parent
    CONFIG_FILE = BASE_DIR / "config.json"
    STATS_FILE = BASE_DIR / ".iptv_stats.json"
    CACHE_FILE = BASE_DIR / ".iptv_cache.json"
    INPUT_FILE = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"

    # 功能开关
    ENABLE_WEB_FETCH = True
    ENABLE_WEB_CHECK = True
    ENABLE_LOCAL_CHECK = True
    ENABLE_SPEED_CHECK = True
    DEBUG_MODE = False
    AUTO_BACKUP = True
    ARCHIVE_FAIL = True

    # 缓存
    ENABLE_CACHE = True
    CACHE_TTL_HOURS = 24

    # 爬虫控制
    MAX_NEW_PLAYLISTS = 200
    PLAYLIST_QUALITY_SCORE = True
    SKIP_WEB_VALIDATE = True
    MAX_SOURCES_TO_CHECK = 0
    MAX_OUTPUT_SOURCES = 2000

    # 性能
    MAX_WORKERS = 120
    FETCH_WORKERS = 20
    TIMEOUT_CN = 8
    TIMEOUT_OVERSEAS = 15
    RETRY_COUNT = 1
    REQUEST_JITTER = False
    MAX_LINKS_PER_NAME = 2
    MAX_SOURCES_PER_DOMAIN = 0

    # FFprobe
    FFPROBE_PROBESIZE = 1000000
    FFPROBE_ANALYZEDURATION = 2000000
    FFPROBE_TIMEOUT_BUFFER = 3

    # 过滤
    FILTER_PRIVATE_IP = True
    REMOVE_REDUNDANT_PARAMS = False
    ENABLE_QUALITY_FILTER = True
    MIN_QUALITY_SCORE = 0
    MIN_SPEED_MBPS = 0.001
    SPEED_CHECK_BYTES = 32768

    # 分辨率
    ENABLE_RESOLUTION_FILTER = False
    MIN_RESOLUTION_WIDTH = 640
    MIN_RESOLUTION_HEIGHT = 480

    # IPv6
    ENABLE_IPV6_OPTIMIZE = True
    IPV6_DEFAULT_DELAY = 0.1
    IPV6_DEFAULT_SPEED = 10.0

    # 代理
    _env_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or os.environ.get('https_proxy') or None
    PROXY = _env_proxy

    # 可持久化配置项
    SAVEABLE_KEYS = {
        'ENABLE_WEB_FETCH', 'ENABLE_WEB_CHECK', 'ENABLE_LOCAL_CHECK',
        'ENABLE_SPEED_CHECK', 'DEBUG_MODE', 'AUTO_BACKUP', 'ARCHIVE_FAIL',
        'MAX_WORKERS', 'FETCH_WORKERS', 'TIMEOUT_CN', 'TIMEOUT_OVERSEAS',
        'RETRY_COUNT', 'REQUEST_JITTER', 'MAX_LINKS_PER_NAME',
        'FILTER_PRIVATE_IP', 'REMOVE_REDUNDANT_PARAMS',
        'ENABLE_QUALITY_FILTER', 'MIN_QUALITY_SCORE', 'PROXY',
        'MAX_SOURCES_PER_DOMAIN', 'WEB_SOURCES', 'MIN_SPEED_MBPS',
        'SPEED_CHECK_BYTES', 'ENABLE_IPV6_OPTIMIZE',
        'IPV6_DEFAULT_DELAY', 'IPV6_DEFAULT_SPEED',
        'ENABLE_CACHE', 'CACHE_TTL_HOURS',
        'ENABLE_RESOLUTION_FILTER', 'MIN_RESOLUTION_WIDTH', 'MIN_RESOLUTION_HEIGHT',
        'SKIP_WEB_VALIDATE', 'MAX_SOURCES_TO_CHECK', 'MAX_OUTPUT_SOURCES',
    }

    # 频道黑名单
    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示",
        "教程", "联系", "推广", "免费", "无效", "过期", "失效", "禁播",
        "视频", "点播", "直播带货", "广告推广"
    }

    # 境外频道关键词
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "BEIN",
        "HOY", "ViuTV", "澳广视", "TDM", "壹电视", "TVBS", "八大",
        "博斯", "澳", "公视", "华文", "八度", "华艺", "Z频道", "GOOD",
        "星空", "寰宇", "GEM", "J2", "开电视", "奇妙电视", "有线宽频",
        "Now TV", "Cable TV", "PCCW", "HKTV", "TTV", "FTV", "TRANSTV",
        "Fuji TV", "WOWOW", "Sky", "DAZN", "Eleven Sports", "SPOTV NOW"
    }

    # 致命错误关键词
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
        "405 method not allowed", "forbidden", "not found"
    }

    # 域名白名单
    PLAYLIST_WHITELIST = {
        "github.com", "githubusercontent.com", "gitlab.com", "gitee.com"
    }

    # 域名黑名单
    PLAYLIST_BLACKLIST_DOMAINS = {
        "shortlink", "bit.ly", "tinyurl", "adf.ly", "link-short", "goo.gl"
    }

    # UA池
    UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'VLC/3.0.18 LibVLC/3.0.18 (LGPLv2.1+)',
        'IINA/1.3.3 (Macintosh; Intel Mac OS X 14.5.0)',
        'PotPlayer/230502 (Windows NT 10.0; x64)',
        'Kodi/21.0 (Omega) Android/13.0.0 Sys_CPU/aarch64',
        'TiviMate/4.7.0 (Android TV)',
        'Perfect Player/1.6.0.1 (Linux;Android 13)',
        'Mozilla/5.0 (Linux; Android 13; TV Box) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Amlogic S905X4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    ]

    # 分类顺序
    CATEGORY_ORDER = [
        "4K 專區", "港澳台頻", "影視劇集", "央視頻道", "衛視綜藝", "體育賽事",
        "少兒動漫", "新聞資訊", "音樂頻道", "其他頻道"
    ]

    # 分类规则（从 config.json 加载时覆盖）
    CATEGORY_RULES_COMPILED: Dict = {}
    CATEGORY_RULES = {}

    # 点播域名黑名单（从 config.json 加载时覆盖）
    VOD_DOMAINS = set()

    # 预设源（从 config.json 加载时覆盖）
    WEB_SOURCES = []
    PRESET_FILES = []

    # 直播频道名关键词
    LIVE_CHANNEL_KEYWORDS = re.compile(
        r'频道|台|卫视|影院|剧场|电影|剧集|直播|体育|音乐|新闻|综合|少儿|动漫|教育|财经|'
        r'Discovery|Channel|TV|News|Live|Sport|Music|Kids|Movie|Film|Drama|Anime'
    )

    @classmethod
    def load_from_file(cls) -> bool:
        """从 config.json 加载配置，覆盖代码默认值"""
        try:
            if not cls.CONFIG_FILE.exists():
                return False
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 加载 sources
            sources = data.get('sources', {})
            cls.PRESET_FILES = sources.get('preset_files', cls.PRESET_FILES)
            cls.WEB_SOURCES = sources.get('web_sources', cls.WEB_SOURCES)
            cls.ENABLE_WEB_FETCH = sources.get('web_fetch_enabled', cls.ENABLE_WEB_FETCH)
            cls.ENABLE_WEB_CHECK = sources.get('web_check_enabled', cls.ENABLE_WEB_CHECK)
            cls.ENABLE_LOCAL_CHECK = sources.get('local_check_enabled', cls.ENABLE_LOCAL_CHECK)

            # 加载 categories
            categories = data.get('categories', {})
            cls.CATEGORY_ORDER = categories.get('order', cls.CATEGORY_ORDER)
            cls.CATEGORY_RULES = categories.get('rules', cls.CATEGORY_RULES)

            # 加载 filter
            filter_cfg = data.get('filter', {})
            cls.BLACKLIST = set(filter_cfg.get('blacklist', list(cls.BLACKLIST)))
            cls.VOD_DOMAINS = set(filter_cfg.get('vod_domains', list(cls.VOD_DOMAINS)))
            cls.OVERSEAS_KEYWORDS = set(filter_cfg.get('overseas_keywords', list(cls.OVERSEAS_KEYWORDS)))
            cls.PLAYLIST_WHITELIST = set(filter_cfg.get('playlist_whitelist', list(cls.PLAYLIST_WHITELIST)))
            cls.PLAYLIST_BLACKLIST_DOMAINS = set(filter_cfg.get('playlist_blacklist', list(cls.PLAYLIST_BLACKLIST_DOMAINS)))

            # 加载 network
            network = data.get('network', {})
            cls.UA_POOL = network.get('user_agents', cls.UA_POOL)
            cls.TIMEOUT_CN = network.get('timeout_cn', cls.TIMEOUT_CN)
            cls.TIMEOUT_OVERSEAS = network.get('timeout_overseas', cls.TIMEOUT_OVERSEAS)
            cls.MAX_WORKERS = network.get('max_workers', cls.MAX_WORKERS)
            cls.FETCH_WORKERS = network.get('fetch_workers', cls.FETCH_WORKERS)

            # 加载 quality
            quality = data.get('quality', {})
            cls.ENABLE_SPEED_CHECK = quality.get('enable_speed_check', cls.ENABLE_SPEED_CHECK)
            cls.MIN_SPEED_MBPS = quality.get('min_speed_mbps', cls.MIN_SPEED_MBPS)
            cls.ENABLE_RESOLUTION_FILTER = quality.get('enable_resolution_filter', cls.ENABLE_RESOLUTION_FILTER)
            cls.MIN_RESOLUTION_WIDTH = quality.get('min_resolution_width', cls.MIN_RESOLUTION_WIDTH)
            cls.MIN_RESOLUTION_HEIGHT = quality.get('min_resolution_height', cls.MIN_RESOLUTION_HEIGHT)

            # 加载 proxy
            proxy = data.get('proxy', {})
            if proxy.get('use_env', True):
                cls.PROXY = cls._env_proxy
            else:
                cls.PROXY = proxy.get('http_proxy', cls._env_proxy)

            return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"Config load error: {e}")
            return False

    @classmethod
    def save_to_file(cls, data=None) -> bool:
        """保存 WEB_SOURCES 到 config.json"""
        try:
            if not cls.CONFIG_FILE.exists():
                return True
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                current = json.load(f)
            if data is not None and isinstance(data, list):
                current.setdefault('sources', {})['web_sources'] = data
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"Config save error: {e}")
            return False

    @classmethod
    def init_compiled_rules(cls):
        """预编译分类正则"""
        if not hasattr(cls, '_compiled'):
            cls._compiled = {
                'noise': re.compile(cls._get_noise_pattern()),
                'bracket_noise': re.compile(cls._get_bracket_noise_pattern()),
                'date_tag': re.compile(cls._get_date_tag_pattern()),
            }
        if not cls.CATEGORY_RULES_COMPILED and cls.CATEGORY_RULES:
            from .utils.name import NameProcessor
            for cat, keywords in cls.CATEGORY_RULES.items():
                simplified = [NameProcessor.simplify(kw) for kw in keywords if kw.strip()]
                if not simplified:
                    cls.CATEGORY_RULES_COMPILED[cat] = re.compile(r'(?=x(?<!x))')
                    continue
                pattern = '|'.join(re.escape(kw) for kw in simplified)
                cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)

    @staticmethod
    def _get_bracket_noise_pattern() -> str:
        patterns = [
            r'\(.*?\)', r'\[.*?\]', r'\{.*?\}',
            r'【.*?】', r'＜.*?＞', r'『.*?』',
            r'「.*?」', r'『.*?』',
            r'（.*?）', r'＜.*?＞'
        ]
        return '|'.join(patterns)

    @staticmethod
    def _get_date_tag_pattern() -> str:
        return Config._get_bracket_noise_pattern()

    @staticmethod
    def _get_noise_pattern() -> str:
        return Config._get_bracket_noise_pattern()
