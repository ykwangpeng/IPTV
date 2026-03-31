import sys, re, time, json, random, argparse, warnings, subprocess, asyncio, logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from functools import lru_cache, wraps
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, urlencode
import threading
import requests
import httpx
import zhconv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 关闭SSL警告
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE  = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    CONFIG_FILE = BASE_DIR / "config.json"

    # 核心功能开关
    ENABLE_WEB_FETCH    = False  # 是否启用自动爬取新增网络直播源的功能（拉取的源质量太低，已禁用）
    ENABLE_WEB_CHECK    = False  # 是否启用拉取并检测预设网络源的功能（默认关闭）
    ENABLE_LOCAL_CHECK  = True   # 是否启用读取并检测本地输入文件的功能
    ENABLE_SPEED_CHECK  = True   # 是否启用下载速度检测
    DEBUG_MODE          = False  # 调试模式开关
    AUTO_BACKUP         = True   # 自动备份开关（备份文件名含时间戳）
    ARCHIVE_FAIL        = True   # 失效源归档开关
    
    # 异步爬虫质量控制 
    MAX_NEW_PLAYLISTS      = 50           # 最多只拉取多少个新播放列表（强烈建议别超过500）
    PLAYLIST_QUALITY_SCORE = True         # 是否启用域名质量评分

    # 性能与超时配置
    MAX_WORKERS         = 80     # 直播源检测的最大并发线程数
    FETCH_WORKERS       = 8      # 网络源拉取的最大并发线程数
    TIMEOUT_CN          = 15     # 境内直播源检测超时时间（秒）
    TIMEOUT_OVERSEAS    = 30     # 境外直播源检测超时时间（秒）
    RETRY_COUNT         = 3      # 网络请求重试次数
    REQUEST_JITTER      = False  # 请求抖动开关
    MAX_LINKS_PER_NAME  = 3      # 每个频道保留的最大有效链接数
    MAX_SOURCES_PER_DOMAIN = 0   # 每个域名最多保留的源数量（0=不限制）

    # 过滤与质量配置
    FILTER_PRIVATE_IP       = True   # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False  # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER   = True   # 质量过滤开关
    MIN_QUALITY_SCORE       = 15     # 最低质量阈值，低于此值过滤（兜底保留最高分1条）
    MIN_SPEED_MBPS          = 0.005  # 最低下载速度阈值（MB/s），低于此值直接判定失效
    SPEED_CHECK_BYTES       = 32768  # 速度检测下载字节数（32KB）
    ENABLE_SPEED_CHECK      = False  # 禁用测速，加快运行速度

    # IPv6 配置（Fix #7: 不再直接满分，改为做真实延迟检测后给予加权分）
    ENABLE_IPV6_OPTIMIZE    = True   # 是否启用 IPv6 优先（不绕过检测，但给予延迟加权）
    IPV6_LATENCY_BONUS      = 10     # IPv6 延迟基础分加权值

    # 代理配置
    PROXY = None                     # 请求使用代理配置

    # 白名单：仅允许从配置文件加载这些字段，防止脏数据覆盖
    SAVEABLE_KEYS = {
        'ENABLE_WEB_FETCH', 'ENABLE_WEB_CHECK', 'ENABLE_LOCAL_CHECK',
        'ENABLE_SPEED_CHECK', 'DEBUG_MODE', 'AUTO_BACKUP', 'ARCHIVE_FAIL',
        'MAX_WORKERS', 'FETCH_WORKERS', 'TIMEOUT_CN', 'TIMEOUT_OVERSEAS',
        'RETRY_COUNT', 'REQUEST_JITTER', 'MAX_LINKS_PER_NAME',
        'FILTER_PRIVATE_IP', 'REMOVE_REDUNDANT_PARAMS',
        'ENABLE_QUALITY_FILTER', 'MIN_QUALITY_SCORE', 'PROXY',
        'MAX_SOURCES_PER_DOMAIN', 'WEB_SOURCES', 'MIN_SPEED_MBPS',
        'SPEED_CHECK_BYTES', 'ENABLE_IPV6_OPTIMIZE', 'IPV6_LATENCY_BONUS'
    }

    # 频道黑名单（含关键词直接过滤）
    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示",
        "教程", "联系", "推广", "免费", "无效", "过期", "失效", "禁播"
    }

    # 境外频道关键词（用于匹配超时时间）
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "BEIN",
        "HOY", "ViuTV", "澳广视", "TDM", "壹电视", "TVBS", "八大"
    }

    # 直播源致命错误关键词（Fix #18: 精确匹配，避免片段误判）
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
        "405 method not allowed"
    }

    # 播放列表域名白名单（用于域名质量评分）
    PLAYLIST_WHITELIST = {
        "github.com", "githubusercontent.com", "gitlab.com", "gitee.com"
    }

    # 播放列表域名黑名单（低质量域名直接跳过）
    PLAYLIST_BLACKLIST_DOMAINS = {
        "shortlink", "bit.ly", "tinyurl", "adf.ly", "link-short", "goo.gl"
    }

    UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
    ]

    # 频道分类顺序（输出文件中的顺序）
    CATEGORY_ORDER = [
        "央衛頻道", "港澳台頻", "影視劇集", "體育賽事",
        "少兒動漫", "衛視綜藝", "紀錄科學", "新聞資訊"
    ]

    # 点播域名黑名单（Fix #6: 精确匹配，避免误伤正常直播流）
    VOD_DOMAINS = {
        "youku.com", "iqiyi.com", "v.qq.com", "mgtv.com", "bilibili.com",
        "tudou.com", "pptv.com", "le.com", "sohu.com"
    }

    # 默认预设网络源列表
    WEB_SOURCES: List[str] = []

    @classmethod
    def load_from_file(cls) -> bool:
        try:
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if key in cls.SAVEABLE_KEYS:
                            setattr(cls, key, value)
                return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"⚠️  配置加载失败: {e}")
        return False

    @classmethod
    def save_to_file(cls, data=None) -> bool:
        try:
            if not cls.CONFIG_FILE.exists():
                return True
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                current = json.load(f)
            # 更新 WEB_SOURCES
            if data is not None and isinstance(data, list):
                current['WEB_SOURCES'] = data
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"⚠️  配置保存失败: {e}")
        return False

    @classmethod
    def init_compiled_rules(cls):
        """初始化编译后的正则表达式"""
        if not hasattr(cls, '_compiled'):
            cls._compiled = {
                'noise': re.compile(cls._get_noise_pattern()),
                'bracket_noise': re.compile(cls._get_bracket_noise_pattern()),
                'date_tag': re.compile(cls._get_date_tag_pattern()),
            }

    @staticmethod
    def _get_bracket_noise_pattern() -> str:
        """合并后的括号噪音模式（Fix #9: 合并 DATE_TAG 与 NOISE）"""
        patterns = [
            r'\(.*?\)', r'\[.*?\]', r'\{.*?\}',
            r'【.*?】', r'＜.*?＞', r'『.*?』',
            r'「.*?」', r'『.*?』',
            r'（.*?）', r'＜.*?＞'
        ]
        return '|'.join(patterns)

    @staticmethod
    def _get_date_tag_pattern() -> str:
        """日期标签模式（Fix #9: 已合并到 BRACKET_NOISE，此处保留向后兼容）"""
        return Config._get_bracket_noise_pattern()

    @staticmethod
    def _get_noise_pattern() -> str:
        """噪音模式（Fix #9: 已合并到 BRACKET_NOISE，此处保留向后兼容）"""
        return Config._get_bracket_noise_pattern()

# ==================== URL清洗与处理 ====================
class URLCleaner:
    @staticmethod
    @lru_cache(maxsize=10000)
    def get_fingerprint(url: str) -> str:
        """URL 指纹提取（带缓存），用于去重"""
        parsed = urlparse(url)
        if Config.REMOVE_REDUNDANT_PARAMS:
            keep_params = {'id', 'token', 'key', 'sign', 'auth', 'code', 'streamid'}
            filtered = {k: v for k, v in parse_qs(parsed.query).items() if k in keep_params}
            query = urlencode(filtered, doseq=True)
        else:
            query = parsed.query
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}" if query else f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @staticmethod
    def _get_hostname(url: str) -> str:
        """提取 hostname（Fix #10: 抽取私有方法统一调用）"""
        return urlparse(url).netloc.lower()

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        """检查是否为内网IP（Fix #10: 使用 _get_hostname 统一）"""
        domain = URLCleaner._get_hostname(url)
        private_patterns = (
            '127.', '0.', 'localhost', '192.168.', '10.', '172.16.', '172.17.',
            '172.18.', '172.19.', '172.20.', '172.21.', '172.22.',
            '172.23.', '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.'
        )
        return any(pattern in domain for pattern in private_patterns)

    @staticmethod
    def is_vod_domain(url: str) -> bool:
        """检查是否为点播域名（Fix #6: 精确匹配）"""
        domain = URLCleaner._get_hostname(url)
        return any(vod in domain for vod in Config.VOD_DOMAINS)

# ==================== M3U解析器 ====================
class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        """解析 M3U 格式"""
        result = []
        name = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF:'):
                # 提取频道名称
                match = re.search(r'tvg-name="([^"]*)"', line)
                if match:
                    name = match.group(1)
                else:
                    # 尝试其他格式
                    match = re.search(r',([^,]+)$', line)
                    if match:
                        name = match.group(1).strip()
            elif line.startswith('http'):
                result.append(f"{name},{line}" if name else f"未知频道,{line}")
                name = None
            elif ',' in line and not line.startswith('#'):
                parts = line.split(',', 1)
                if len(parts) == 2:
                    name, url = parts
                    name = name.strip()
                    url = url.strip()
                    if url.startswith('http'):
                        result.append(f"{name},{url}")
        return result

    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        """解析纯文本格式（每行：名称,URL）"""
        result = []
        for line in lines:
            line = line.strip()
            if ',' in line:
                name, url = line.split(',', 1)
                name = name.strip()
                url = url.strip()
                if url.startswith('http'):
                    result.append(f"{name},{url}")
        return result

# ==================== 名称处理器 ====================
class NameProcessor:
    @staticmethod
    @lru_cache(maxsize=10000)
    def normalize(name: str) -> str:
        """频道名称标准化：繁简转换 + 噪音清理"""
        # 繁简转换
        name = zhconv.convert(name, 'zh-cn')
        # 清理括号噪音
        if hasattr(Config, '_compiled'):
            name = re.sub(Config._compiled['bracket_noise'], '', name)
        # 清理多余空格
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    @staticmethod
    def is_overseas(name: str) -> bool:
        """判断是否为境外频道"""
        return any(keyword in name for keyword in Config.OVERSEAS_KEYWORDS)

    @staticmethod
    def is_blacklisted(name: str) -> bool:
        """判断是否在黑名单中"""
        normalized = NameProcessor.normalize(name)
        return any(keyword in normalized for keyword in Config.BLACKLIST)

# ==================== 分类器 ====================
class CategoryClassifier:
    CATEGORY_KEYWORDS = {
        "央衛頻道": [
            "CCTV", "央视频道", "中央一台", "中央二台", "中央三台", "中央四台",
            "中央五台", "中央六台", "中央七台", "中央八台", "中央九台",
            "中央十台", "中央十一台", "中央十二台", "中央十三台", "中央十四台",
            "中央十五台", "中央十六台", "中央十七台", "中央新闻", "中央财经",
            "中央综合", "国防军事", "戏曲音乐", "农业农村", "纪录", "少儿",
            "音乐", "戏曲", "CGTN", "CCTV4K", "CCTV8K"
        ],
        "港澳台頻": [
            "凤凰卫视", "翡翠台", "明珠台", "本港台", "亚洲电视", "香港卫视",
            "台湾电视", "台视", "华视", "民视", "东森", "三立", "纬来",
            "中天", "非凡", "龙祥", "靖天", "爱尔达", "TVBS", "八大",
            "壹电视", "澳广视", "TDM", "ViuTV", "HOY"
        ],
        "影視劇集": [
            "电影", "电视剧", "综艺", "动漫", "影院", "剧场", "影院",
            "Netflix", "HBO", "迪士尼", "华纳", "索尼", "派拉蒙", "环球",
            "腾讯视频", "爱奇艺", "优酷", "哔哩哔哩", "芒果TV", "搜狐视频",
            "PPTV", "乐视", "酷开", "暴风", "奇异果", "优土"
        ],
        "體育賽事": [
            "体育", "足球", "篮球", "网球", "高尔夫", "棒球", "斯诺克",
            "F1", "NBA", "英超", "西甲", "意甲", "德甲", "法甲", "中超",
            "CBA", "羽球", "乒乓球", "围棋", "象棋", "棋牌"
        ],
        "少兒動漫": [
            "少儿", "儿童", "动画", "卡通", "幼儿园", "幼教", "贝瓦",
            "小伴龙", "宝宝巴士", "巧虎", "小猪佩奇", "汪汪队",
            "超级飞侠", "萌鸡小队", "猪猪侠"
        ],
        "衛視綜藝": [
            "卫视", "湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视",
            "广东卫视", "山东卫视", "四川卫视", "安徽卫视", "天津卫视",
            "河北卫视", "河南卫视", "湖北卫视", "江西卫视", "重庆卫视",
            "福建卫视", "辽宁卫视", "深圳卫视", "广西卫视", "黑龙江卫视",
            "云南卫视", "陕西卫视", "甘肃卫视", "贵州卫视", "山西卫视"
        ],
        "紀錄科學": [
            "纪录片", "探索", "科学", "自然", "动物", "地理", "历史",
            "国家地理", "Discovery", "BBC", "历史频道"
        ],
        "新聞資訊": [
            "新闻", "资讯", "财经", "股票", "气象", "交通", "旅游",
            "新闻台", "资讯台", "财经台"
        ]
    }

    @staticmethod
    @lru_cache(maxsize=10000)
    def classify(name: str) -> str:
        """频道分类"""
        for category, keywords in CategoryClassifier.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name:
                    return category
        return "其他"

# ==================== 网络源获取器 ====================
class WebSourceFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        requests.packages.urllib3.disable_warnings()

    def fetch(self, url: str, proxy: Optional[str] = None) -> Optional[List[str]]:
        """拉取网络源并解析"""
        if not url:
            return None
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        headers = {'User-Agent': random.choice(Config.UA_POOL)}
        try:
            # 境内源超时短，境外源超时长
            timeout = 15 if url.startswith('https://github.com') else 20
            resp = self.session.get(url, headers=headers, proxies=proxies, timeout=timeout)
            if resp.status_code == 200 and len(resp.text) > 100:
                lines = resp.text.splitlines()
                if any(l.startswith('#EXTM3U') for l in lines[:10]):
                    return M3UParser.parse(lines)
                else:
                    return M3UParser._parse_plain_text(lines)
            return None
        except Exception as e:
            if Config.DEBUG_MODE:
                print(f"⚠️ 拉取异常 {url}: {e}")
            return []

# ==================== 异步网络源爬虫 ====================
class AsyncWebSourceCrawler:
    """异步爬虫 - 优质源版：严格控制数量 + 域名质量评分"""

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
        self.new_playlists: Set[str] = set()

    @property
    def SOURCE_SITES(self):
        return Config.WEB_SOURCES

    async def __aenter__(self):
        timeout = httpx.Timeout(8.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30, keepalive_expiry=15.0)
        self.session = httpx.AsyncClient(timeout=timeout, limits=limits, verify=False, follow_redirects=True)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 1.5) -> bool:
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        }
        try:
            resp = await self.session.head(url, headers=headers, timeout=timeout, follow_redirects=True)
            if resp.status_code in (200, 206, 301, 302, 304):
                return True
            async with self.session.stream('GET', url, headers=headers, timeout=timeout) as resp:
                if resp.status_code in (200, 206):
                    await resp.aread(1024)
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def _get_domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    @staticmethod
    def _is_high_quality(url: str) -> int:
        """域名质量评分：白名单最高分，黑名单直接0"""
        domain = AsyncWebSourceCrawler._get_domain(url)
        if any(bad in domain for bad in Config.PLAYLIST_BLACKLIST_DOMAINS):
            return 0
        if any(good in domain for good in Config.PLAYLIST_WHITELIST):
            return 100
        # 普通 github/raw 给中等分
        if "githubusercontent.com" in domain or "github.com" in domain:
            return 70
        return 30  # 其他域名低分

    @staticmethod
    def _is_playlist(url: str) -> bool:
        """判断 URL 是否为播放列表（排除带鉴权参数的单个直播流）"""
        lower = url.lower()

        # 修复方案B：排除带鉴权参数的单个流 URL（userid/sign/auth_token 表示时效性鉴权）
        auth_params = ('userid=', 'sign=', 'auth_token=', 'token=', 'session=')
        if any(param in lower for param in auth_params):
            return False

        # 单个数字或 ID 的 .m3u8 通常也是单流，不是播放列表
        path = urlparse(url).path
        if path.endswith('.m3u8'):
            # 提取文件名（不含扩展名），如果纯数字或短字母则是单流
            filename = Path(path).stem
            if filename.isdigit() or len(filename) <= 10:
                return False

        return any(ext in lower for ext in AsyncWebSourceCrawler.PLAYLIST_EXT)

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        if depth > 1 or len(self.new_playlists) >= Config.MAX_NEW_PLAYLISTS:
            return set()

        try:
            headers = {'User-Agent': random.choice(Config.UA_POOL)}
            resp = await self.session.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200 or len(resp.text) < 100:
                return set()

            playlists = set()
            for pattern in self.URL_PATTERNS:
                for match in re.findall(pattern, resp.text, re.IGNORECASE):
                    if len(match) < 15 or match in self.all_extracted:
                        continue
                    self.all_extracted.add(match)

                    if self._is_playlist(match):
                        score = self._is_high_quality(match)
                        if score >= 30:                     # 只保留中等以上质量
                            playlists.add(match)
                            self.new_playlists.add(match)   # 全局计数

            # 递归只爬优质播放列表
            if depth < 1 and playlists:
                for p in list(playlists)[:5]:   # 每次只递归5个，避免爆炸
                    await self.extract_sources_from_content(p, depth + 1)

            return playlists
        except Exception:
            return set()

    async def crawl_single_source(self, url: str, semaphore: asyncio.Semaphore) -> Set[str]:
        async with semaphore:
            try:
                if not await self.quick_validate(url, 2.5):
                    return set()
                return await self.extract_sources_from_content(url)
            except Exception:
                return set()

    async def crawl_all(self) -> Set[str]:
        print("🔍 启动异步爬虫（优质模式）...")
        semaphore = asyncio.Semaphore(12)
        tasks = [self.crawl_single_source(url, semaphore) for url in self.SOURCE_SITES]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 最终去重 + 按质量排序 + 数量限制
        final_list = sorted(
            self.new_playlists,
            key=lambda u: self._is_high_quality(u),
            reverse=True
        )[:Config.MAX_NEW_PLAYLISTS]

        print(f"✅ 爬虫完成！优质播放列表 {len(final_list)} 个（已过滤掉 {len(self.new_playlists)-len(final_list)} 个垃圾源）")
        return set(final_list)

# ==================== 流检测器 ====================
class StreamChecker:
    @staticmethod
    def check(line: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """检测单条直播源，返回质量数据或 None（失效）"""
        try:
            if ',' not in line:
                return None
            name_part, url_part = line.split(',', 1)
            name = name_part.strip()[:100]
            url = url_part.strip()

            # 基础校验
            if not name or not url:
                return None
            if NameProcessor.is_blacklisted(name):
                return None
            if URLCleaner.filter_private_ip(url):
                return None
            if URLCleaner.is_vod_domain(url):
                return None
            if not url.startswith(('http://', 'https://')):
                return None

            # 检测超时配置
            is_overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if is_overseas else Config.TIMEOUT_CN

            # 使用 ffprobe 检测（完全按照原始版本）
            start_time = time.time()
            domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\n'

            cmd = [
                'ffprobe', '-headers', headers_str, '-v', 'error',
                '-show_entries', 'stream=codec_type:format=duration,format_name',
                '-probesize', '10000000', '-analyzeduration', '20000000',
                '-timeout', str(int(timeout * 1_000_000)), '-reconnect_streamed', '1',
                '-reconnect_delay_max', '3',
                '-err_detect', 'ignore_err', '-fflags', 'nobuffer+flush_packets',
                '-user_agent', random.choice(Config.UA_POOL),
            ]

            if Config.PROXY:
                cmd.extend(['-http_proxy', Config.PROXY])
            cmd.append(url)

            proc = None
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
                stdout, stderr = proc.communicate(timeout=timeout + 3)

                stdout_text = stdout.decode('utf-8', errors='ignore').lower()
                stderr_text = stderr.decode('utf-8', errors='ignore').lower()

                has_fatal = any(kw in stderr_text for kw in Config.FATAL_ERROR_KEYWORDS)
                has_stream = 'codec_type=video' in stdout_text or 'codec_type=audio' in stdout_text

                if not has_fatal and has_stream:
                    latency = round(time.time() - start_time, 2)
                    quality = StreamChecker._calc_quality_score(latency, 0)
                    return {
                        "status": "有效", "name": name, "url": url, "lat": latency,
                        "overseas": is_overseas, "quality": quality
                    }

            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                    proc.communicate()
            except Exception:
                if proc:
                    proc.kill()
                    proc.communicate()

            # 降级 HTTP 快速检测（ffprobe 失败后尝试）
            try:
                headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain}
                proxies = {'http': proxy, 'https': proxy} if proxy else None
                start_time = time.time()
                resp = requests.head(url, headers=headers, timeout=timeout//2,
                                    allow_redirects=True, proxies=proxies)

                if resp.status_code in (200, 206, 301, 302, 304):
                    latency = round(time.time() - start_time, 2)
                    quality = StreamChecker._calc_quality_score(latency, 0)
                    return {
                        "status": "有效", "name": name, "url": url, "lat": latency,
                        "overseas": is_overseas, "quality": quality
                    }
            except Exception:
                pass

            return None

        except Exception:
            return None

    @staticmethod
    def _calc_quality_score(latency: float, retries: int) -> int:
        if latency <= 1:
            return 100
        elif latency <= 3:
            return 80
        elif latency <= 5:
            return 60
        elif latency <= 10:
            return 40
        else:
            return 20

    @staticmethod
    def check_speed(url: str, proxy: Optional[str] = None) -> float:
        """检测下载速度（MB/s）"""
        if not Config.ENABLE_SPEED_CHECK:
            return 0.0

        proxies = {'http': proxy, 'https': proxy} if proxy else None
        headers = {'User-Agent': random.choice(Config.UA_POOL)}

        try:
            start_time = time.time()
            resp = requests.get(url, headers=headers, proxies=proxies,
                             stream=True, timeout=Config.TIMEOUT_CN + 5)
            total_bytes = 0
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    total_bytes += len(chunk)
                if total_bytes >= Config.SPEED_CHECK_BYTES:
                    break
            elapsed = time.time() - start_time
            speed_mbps = (total_bytes / elapsed) / 1024 / 1024
            return speed_mbps
        except Exception:
            return 0.0

# ==================== 主控制器 ====================
class IPTVChecker:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if Config.DEBUG_MODE:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats   = {
            'total': 0, 'valid': 0, 'failed': 0,
            'by_overseas': {'cn': 0, 'overseas': 0},
            'by_category': {cat: 0 for cat in Config.CATEGORY_ORDER},
            'filtered_by_quality': 0
        }

    def backup_output(self, output_file: Path) -> bool:
        """备份原输出文件"""
        if not output_file.exists() or not Config.AUTO_BACKUP:
            return False
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        backup_file = output_file.with_name(f"{output_file.stem}_backup_{timestamp}.txt")
        output_file.rename(backup_file)
        self.logger.info(f"📦 备份原文件: {backup_file.name}")
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]):
        """源数据预处理：名称清洗→有效性校验→指纹去重→域名分组"""
        debug_filtered = 0
        debug_total = len(lines)
        for line in lines:
            if ',' not in line:
                debug_filtered += 1
                continue
            name_part, url_part = line.split(',', 1)
            name = name_part.strip()
            url = url_part.strip()

            # 有效性校验
            if not name or name == '未知频道':
                debug_filtered += 1
                continue
            if NameProcessor.is_blacklisted(name):
                debug_filtered += 1
                continue
            if URLCleaner.filter_private_ip(url):
                debug_filtered += 1
                continue
            if URLCleaner.is_vod_domain(url):
                debug_filtered += 1
                continue
            if not url.startswith(('http://', 'https://')):
                debug_filtered += 1
                continue

            fp = URLCleaner.get_fingerprint(url)
            if fp in seen_fp:
                debug_filtered += 1
                continue
            seen_fp.add(fp)
            # Fix #2: 使用 _get_hostname 复用解析逻辑
            domain = URLCleaner._get_hostname(url)
            domain_lines[domain].append(f"{name},{url}")
        
        if Config.DEBUG_MODE and debug_filtered > 0:
            self.logger.debug(f"🔍 process_lines: 过滤 {debug_filtered}/{debug_total} 条，保留 {debug_total-debug_filtered} 条")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        """同步运行主流程"""
        seen_fp      = pre_seen_fp      if pre_seen_fp      is not None else set()
        domain_lines = pre_domain_lines if pre_domain_lines is not None else defaultdict(list)
        lines_to_check: List[str] = []

        # 1. 处理本地文件
        if Config.ENABLE_LOCAL_CHECK:
            input_path = args.input if args.input else str(Config.INPUT_FILE)
            self.logger.info(f"📂 读取本地文件：{input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    local_lines = [l.strip() for l in f if l.strip()]
                self.process_lines(local_lines, seen_fp, domain_lines)
                self.logger.info(f"✅ 本地文件处理完成：{len(local_lines)}条")
            except Exception as e:
                self.logger.error(f"❌ 读取本地文件失败: {e}")

        # 2. 拉取预设网络源
        if Config.ENABLE_WEB_CHECK:
            web_sources = Config.WEB_SOURCES
            if not web_sources and Config.CONFIG_FILE.exists():
                Config.load_from_file()
                web_sources = Config.WEB_SOURCES

            if web_sources:
                self.logger.info(f"🌐 并发拉取 {len(web_sources)} 个预设网络源...")
                with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                    future_to_url = {executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                                     for url in web_sources}
                    success_count = fail_count = total_extracted = 0
                    successful_web_sources = []
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            fetched = future.result()
                            if fetched:
                                self.process_lines(fetched, seen_fp, domain_lines)
                                success_count  += 1
                                total_extracted += len(fetched)
                                self.logger.info(f"✅ 拉取成功: {url} ({len(fetched)}条)")
                                successful_web_sources.append(url)
                            else:
                                fail_count += 1
                                self.logger.warning(f"❌ 拉取失败: {url} - 返回空内容")
                        except Exception as e:
                            fail_count += 1
                            self.logger.error(f"❌ 拉取异常: {url} - {e}")
                self.logger.info(f"📊 网络源拉取完成: 成功{success_count}/{len(web_sources)} | "
                             f"失败{fail_count} | 提取{total_extracted}条")
                if successful_web_sources:
                    Config.save_to_file(successful_web_sources)

        # 3. 收集待测源
        if Config.MAX_SOURCES_PER_DOMAIN <= 0:
            for urls in domain_lines.values():
                lines_to_check.extend(urls)
        else:
            for urls in domain_lines.values():
                lines_to_check.extend(urls[:Config.MAX_SOURCES_PER_DOMAIN])

        total = len(lines_to_check)
        if total == 0:
            self.logger.warning("⚠️ 没有可检测的直播源，程序退出")
            return
        self.stats['total'] = total

        overseas_total = sum(1 for ln in lines_to_check if NameProcessor.is_overseas(ln.split(',', 1)[0]))
        self.logger.info(f"📋 待测源统计: 总计 {total} 条 | 境内 {total - overseas_total} 条 | 境外 {overseas_total} 条")

        cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list: List[str] = []
        real_workers = min(args.workers, total)
        self.logger.info(f"🚀 启动并发检测：{real_workers}个工作线程")

        # 4. 并发测活
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="测活中", unit="源", ncols=90,
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            # 绑定 future 与对应的 ln，修复 NameError
            future_to_ln = {executor.submit(self.checker.check, ln, Config.PROXY): ln for ln in lines_to_check}
            done_count = 0
            for future in as_completed(future_to_ln):
                ln = future_to_ln[future]  # 取出当前任务对应的源行
                r = future.result()
                if r:
                    self.stats['valid'] += 1
                    if r['overseas']:
                        self.stats['by_overseas']['overseas'] += 1
                    else:
                        self.stats['by_overseas']['cn'] += 1
                    # 分类
                    category = CategoryClassifier.classify(r['name'])
                    if category in cat_map:
                        cat_map[category].append(r)
                else:
                    self.stats['failed'] += 1
                    fail_list.append(ln)
                done_count += 1
                # 更新进度条，显示实时有效率
                valid_percent = (self.stats['valid'] / done_count * 100) if done_count > 0 else 0
                pbar.set_postfix_str(f'有效{self.stats["valid"]}/{done_count} 有效率:{valid_percent:.1f}%')
                pbar.update(1)

        # 5. 速度检测（可选）
        if Config.ENABLE_SPEED_CHECK:
            self.logger.info(f"⏳ 开始速度检测...")
            valid_sources = [ch for cat_chs in cat_map.values() for ch in cat_chs]
            for channel_data in tqdm(valid_sources, desc="测速中", unit="条", ncols=80,
                                     bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{percentage:.0f}%] [{elapsed}<{remaining}, {rate_fmt}]'):
                speed = self.checker.check_speed(channel_data['url'], Config.PROXY)
                if speed < Config.MIN_SPEED_MBPS:
                    # 速度太慢，移除
                    for cat_chs in cat_map.values():
                        if channel_data in cat_chs:
                            cat_chs.remove(channel_data)
                            self.stats['filtered_by_quality'] += 1
                            break
                else:
                    # 速度分数加入质量分
                    channel_data['quality'] += int(speed * 10)

        # 6. 写入结果文件
        output_file = args.output if args.output else str(Config.OUTPUT_FILE)
        self.write_results(output_file, cat_map, total, fail_list)

    async def run_async(self, args):
        """异步运行模式 - 优质播放列表版（已彻底修复）"""
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)

        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            self.logger.info("🌐 启动异步爬虫（优质模式）...")
            async with AsyncWebSourceCrawler() as crawler:
                new_playlists = await crawler.crawl_all()   # 新版爬虫只返回播放列表

                # 处理新发现的优质播放列表
                if new_playlists:
                    self.logger.info(f"📥 发现 {len(new_playlists)} 个优质播放列表，开始并发拉取...")
                    # 添加超时保护，避免线程池卡住
                    import concurrent.futures
                    with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                        future_to_url = {
                            executor.submit(self.fetcher.fetch, pl_url, Config.PROXY): pl_url
                            for pl_url in new_playlists
                        }
                        # 设置超时，每30秒检查一次
                        done_count = 0
                        total_futures = len(future_to_url)
                        while done_count < total_futures:
                            # 使用 wait + timeout 避免永久阻塞
                            done, not_done = concurrent.futures.wait(
                                list(future_to_url.keys()),
                                timeout=30,
                                return_when=concurrent.futures.FIRST_COMPLETED
                            )
                            for future in done:
                                pl_url = future_to_url[future]
                                done_count += 1
                                try:
                                    fetched = future.result()
                                    if fetched:
                                        if Config.DEBUG_MODE:
                                            self.logger.debug(f"🔍 调试: {pl_url} 返回 {len(fetched)} 条源，预览前3条")
                                            for i, line in enumerate(fetched[:3]):
                                                self.logger.debug(f"  {i+1}. {line[:100]}")
                                        self.process_lines(fetched, seen_fp, domain_lines)
                                        self.logger.info(f"✅ 新播放列表拉取成功: {pl_url} ({len(fetched)}条)")
                                except Exception as e:
                                    self.logger.warning(f"⚠️ 新播放列表拉取失败 {pl_url}: {e}")
                                # 修复：从字典中移除已完成的 future，避免无限循环
                                del future_to_url[future]
                            # 如果还有未完成的任务但没有新的完成，打印进度
                            if not_done and done_count < total_futures:
                                self.logger.info(f"⏳ 进度: {done_count}/{total_futures}...")
                    
                    # 调试：显示处理后的源数量
                    total_crawled = sum(len(urls) for urls in domain_lines.values())
                    if Config.DEBUG_MODE and domain_lines:
                        self.logger.info(f"🔍 调试信息：域名数量={len(domain_lines)}, 预览前3个域名")
                        for i, (domain, urls) in enumerate(list(domain_lines.items())[:3]):
                            self.logger.info(f"  {i+1}. {domain}: {len(urls)}条源")
                    self.logger.info(f"📊 异步爬虫累计源: {total_crawled} 条")

        # 继续走原有主检测流程
        self.run(args, pre_seen_fp=seen_fp, pre_domain_lines=domain_lines)

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int, fail_list: Optional[List[str]] = None):
        """写入结果文件，空分类不写入，质量过滤增加兜底"""
        output_path = Path(output_file)
        tmp_path    = output_path.with_suffix('.tmp')
        total_written = 0

        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for cat in Config.CATEGORY_ORDER:
                    channels = cat_map.get(cat, [])

                    # Fix #5: 分组同时完成质量过滤
                    grouped = defaultdict(list)
                    for ch in channels:
                        if Config.ENABLE_QUALITY_FILTER and ch['quality'] < Config.MIN_QUALITY_SCORE:
                            self.stats['filtered_by_quality'] += 1
                            continue
                        grouped[ch['name']].append(ch)
                        self.stats['by_category'][cat] += 1

                    total_channels_in_cat = sum(len(items) for items in grouped.values())
                    if total_channels_in_cat <= 0:
                        continue

                    f.write(f"{cat},#genre#\n")
                    total_written += total_channels_in_cat

                    # 央衛頻道特殊排序（保持原有逻辑）
                    if cat == "央衛頻道":
                        # CCTV1-17 固定在前面
                        cctv_1_to_17 = []
                        other_cctv = []
                        for name in sorted(grouped.keys()):
                            match = re.search(r'CCTV(\d+)', name)
                            if match:
                                num = int(match.group(1))
                                if 1 <= num <= 17:
                                    cctv_1_to_17.append((num, name))
                                else:
                                    other_cctv.append(name)
                            elif "央視頻道" in name or "中央" in name or "央视" in name:
                                other_cctv.append(name)

                        # 写入 CCTV1-17
                        cctv_1_to_17.sort()
                        for _, name in cctv_1_to_17:
                            self._write_channel(f, grouped[name], Config.MAX_LINKS_PER_NAME)

                        # 写入 CCTV5+（如果有）
                        if "CCTV5+" in grouped:
                            self._write_channel(f, grouped["CCTV5+"], Config.MAX_LINKS_PER_NAME)

                        # 写入其他 CCTV 和 中央台
                        other_cctv_sorted = sorted(grouped.keys(), key=lambda n: 0 if n == "CCTV5+" else 1)
                        for name in other_cctv_sorted:
                            self._write_channel(f, grouped[name], Config.MAX_LINKS_PER_NAME)

                        # 写入卫视（按质量降序）
                        satellite_channels = [ch for name, items in grouped.items()
                                          if any(sw in name for sw in ["卫视", "卫星电视"])]
                        for ch in sorted(satellite_channels, key=lambda x: x['quality'], reverse=True):
                            self._write_channel(f, [ch], Config.MAX_LINKS_PER_NAME)
                    else:
                        # 其他分类按质量降序
                        for channels_list in sorted(grouped.values(),
                                              key=lambda lst: max(ch['quality'] for ch in lst),
                                              reverse=True):
                            self._write_channel(f, channels_list, Config.MAX_LINKS_PER_NAME)

        except Exception as e:
            self.logger.error(f"❌ 写入结果失败: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            raise e

        # 原子文件替换
        if tmp_path.exists():
            if output_path.exists():
                output_path.unlink()
            tmp_path.rename(output_path)

        # 打印统计
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: 总计 {total} 条")
        self.logger.info(f"✅ 测活有效: {self.stats['valid']} 条 | 失效: {self.stats['failed']} 条")
        self.logger.info(f"⚠️  质量过滤: {self.stats['filtered_by_quality']} 条 | 最终写入: {total_written} 条")
        self.logger.info(f"✅ 整体有效率: {self.stats['valid']/total*100:.1f}%")
        self.logger.info(f"📊 境内有效: {self.stats['by_overseas']['cn']} 条 | 境外有效: {self.stats['by_overseas']['overseas']} 条")
        self.logger.info(f"📋 分类有效统计:")
        for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: -x[1]):
            self.logger.info(f"  {cat}: {count} 条")

        # 失效源归档
        if Config.ARCHIVE_FAIL and fail_list:
            fail_file = output_path.with_name(f"{output_path.stem}_fail.txt")
            with open(fail_file, 'w', encoding='utf-8') as f:
                for line in fail_list:
                    f.write(f"{line}\n")
            self.logger.info(f"📦 失效源已归档: {fail_file.name}")

    def _write_channel(self, f, channels: List[Dict], max_links: int):
        """写入单个频道的数据（格式：频道名,URL）"""
        if not channels:
            return
        # 按质量降序，保留前 N 条
        sorted_channels = sorted(channels, key=lambda x: x['quality'], reverse=True)[:max_links]
        for ch in sorted_channels:
            f.write(f"{ch['name']},{ch['url']}\n")

# ==================== 命令行入口 ====================
def main():
    # 检测 ffprobe
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            print("✅ ffprobe 正常")
        else:
            print("❌ ffprobe 不可用，请安装 FFmpeg")
            sys.exit(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("❌ ffprobe 不可用，请安装 FFmpeg")
        sys.exit(1)

    # 初始化配置
    Config.load_from_file()
    Config.init_compiled_rules()

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 - Apex Lity 版')
    parser.add_argument('-i', '--input', default=str(Config.INPUT_FILE), help='输入文件路径')
    parser.add_argument('-o', '--output', default=str(Config.OUTPUT_FILE), help='输出文件路径')
    parser.add_argument('-w', '--workers', type=int, default=Config.MAX_WORKERS, help='并发检测线程数')
    parser.add_argument('-t', '--timeout', type=int, default=Config.TIMEOUT_CN, help='境内源超时时间(秒)')
    parser.add_argument('--proxy', default=None, help='代理地址 (如 http://127.0.0.1:7890)')
    parser.add_argument('--no-web', action='store_true', help='跳过预设网络源拉取')
    parser.add_argument('--async-crawl', action='store_true', help='启用异步爬虫扫描新源')
    parser.add_argument('--no-speed-check', action='store_true', help='关闭下载速度检测')
    args = parser.parse_args()

    if args.timeout:
        Config.TIMEOUT_CN = args.timeout
        Config.TIMEOUT_OVERSEAS = args.timeout * 2

    if args.workers:
        Config.MAX_WORKERS = args.workers

    if args.no_speed_check:
        Config.ENABLE_SPEED_CHECK = False

    print(f"{'='*60}\n")

    checker = IPTVChecker()

    # 备份原文件
    output_file = Path(args.output if args.output else str(Config.OUTPUT_FILE))
    checker.backup_output(output_file)

    try:
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            asyncio.run(checker.run_async(args))
        else:
            checker.run(args)
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断程序")
    except Exception as e:
        checker.logger.error(f"❌ 程序异常: {e}")
        raise

if __name__ == '__main__':
    main()
