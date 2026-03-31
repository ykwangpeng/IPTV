import sys, re, time, json, random, argparse, warnings, subprocess, asyncio, logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from functools import lru_cache, wraps
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, urlencode, urljoin
import threading
import requests
import httpx
import zhconv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ✅ 新增：M3U8 解析库
try:
    import m3u8
    M3U8_AVAILABLE = True
except ImportError:
    M3U8_AVAILABLE = False

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE  = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    CONFIG_FILE = BASE_DIR / "config.json"
    CACHE_FILE  = BASE_DIR / "speed_cache.json"
    STATS_FILE  = BASE_DIR / "stats.json"

    ENABLE_WEB_FETCH    = False # 是否启用自动爬取新增网络直播源的功能
    ENABLE_WEB_CHECK    = False # 是否启用拉取并检测预设网络源的功能
    ENABLE_LOCAL_CHECK  = True  # 是否启用读取并检测本地输入文件的功能

    DEBUG_MODE          = False  # 调试模式开关
    AUTO_BACKUP         = True   # 自动备份开关（备份文件名含时间戳）
    ARCHIVE_FAIL        = True   # 失效源归档开关
    MAX_WORKERS         = 80     # 直播源检测的最大并发线程数
    FETCH_WORKERS       = 8      # 网络源拉取的最大并发线程数
    TIMEOUT_CN          = 8      # 境内直播源检测超时时间（秒）
    TIMEOUT_OVERSEAS    = 15     # 境外直播源检测超时时间（秒）
    RETRY_COUNT         = 2      # 网络请求重试次数
    REQUEST_JITTER      = False  # 请求抖动开关
    MAX_LINKS_PER_NAME  = 3      # 每个频道保留的最大有效链接数
    FILTER_PRIVATE_IP   = True   # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False  # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER   = False  # 质量过滤开关（建议关闭：ffprobe 已做流级别验证，无需二次筛选）
    MIN_QUALITY_SCORE       = 60     # 最低质量评分阈值
    PROXY = None                     # 请求使用代理配置

    # ✅ 新增：速度检测配置（借鉴 Guovin）
    ENABLE_SPEED_TEST       = True   # 是否启用下载速度检测
    SPEED_TEST_TIMEOUT      = 5      # 速度检测超时（秒）
    SPEED_TEST_MIN_BYTES    = 65536  # 最小下载字节数（64KB）
    SPEED_TEST_MIN_TIME     = 1.0    # 最小测量时间（秒）
    MIN_SPEED_MBPS          = 0.5    # 最低下载速度阈值（MB/s）

    # ✅ 新增：分辨率检测配置
    ENABLE_RESOLUTION_TEST  = True   # 是否启用分辨率检测
    MIN_RESOLUTION_HEIGHT   = 480    # 最低分辨率高度（像素）

    # ✅ 新增：缓存配置
    ENABLE_CACHE            = True   # 是否启用测试结果缓存
    CACHE_EXPIRE_HOURS      = 24     # 缓存过期时间（小时）

    # ✅ 新增：IPv6 优化配置（借鉴 Guovin）
    ENABLE_IPV6_OPTIMIZE    = True   # 是否启用 IPv6 优化
    IPV6_DEFAULT_DELAY      = 0.1    # IPv6 默认延迟（秒）
    IPV6_DEFAULT_SPEED      = float('inf')  # IPv6 默认速度

    # ✅ 新增：稳定性检测配置（借鉴 Guovin）
    STABILITY_WINDOW        = 4      # 稳定性窗口大小
    STABILITY_THRESHOLD     = 0.12   # 稳定性阈值（波动 < 12%）

    # ✅ 新增：M3U8 多码率解析
    ENABLE_M3U8_PARSE       = True   # 是否解析 M3U8 多码率

    # ✅ 白名单：只允许从 config.json 加载这些标量/列表字段
    SAVEABLE_KEYS = {
        'ENABLE_WEB_FETCH', 'ENABLE_WEB_CHECK', 'ENABLE_LOCAL_CHECK',
        'DEBUG_MODE', 'AUTO_BACKUP', 'ARCHIVE_FAIL',
        'MAX_WORKERS', 'FETCH_WORKERS', 'TIMEOUT_CN', 'TIMEOUT_OVERSEAS',
        'RETRY_COUNT', 'REQUEST_JITTER', 'MAX_LINKS_PER_NAME',
        'FILTER_PRIVATE_IP', 'REMOVE_REDUNDANT_PARAMS',
        'ENABLE_QUALITY_FILTER', 'MIN_QUALITY_SCORE', 'PROXY',
        'MAX_SOURCES_PER_DOMAIN', 'ENABLE_SPEED_TEST', 'SPEED_TEST_TIMEOUT',
        'MIN_SPEED_MBPS', 'ENABLE_RESOLUTION_TEST', 'MIN_RESOLUTION_HEIGHT',
        'ENABLE_CACHE', 'CACHE_EXPIRE_HOURS',
        'ENABLE_IPV6_OPTIMIZE', 'IPV6_DEFAULT_DELAY',
        'STABILITY_WINDOW', 'STABILITY_THRESHOLD', 'ENABLE_M3U8_PARSE',
    }

    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示",
        "教程", "联系", "推广", "免费"
    }
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "BEIN",
    }
    # ✅ 借鉴 Apex111：ffprobe stderr 致命错误关键字（命中则判定失效）
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
    }

    CATEGORY_RULES_COMPILED: Dict = {}

    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "咪咕", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "MLS", "F1", "MotoGP",
            "WWE", "UFC", "拳击", "高尔夫", "GOLF", "ATP", "WTA", "奥运", "亚运",
        ],
        "音樂頻道": [
            "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV",
            "流行", "嘻哈", "摇滚", "古典", "爵士", "民谣", "电音", "EDM",
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼", "宝宝", "宝贝",
            "炫动", "CARTOON", "ANIME", "ANIMATION", "KIDS", "DISNEY", "尼克",
        ],
        "影視劇集": [
            "爱奇艺", "优酷", "腾讯视频", "芒果 TV", "IQIYI", "剧集", "电影", "影院",
            "影视", "剧场", "Hallmark", "龙华", "NETFLIX", "HBO", "电视剧", "网剧",
        ],
        "港澳台頻": [
            "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理",
            "香港", "华文", "八度", "华艺", "生命", "镜", "澳", "台湾", "探索",
            "年代", "明珠", "唯心", "公视", "东森", "三立", "爱尔达", "NOW", "VIU",
            "STAR", "星空", "纬来", "非凡", "中天", "中视", "无线", "寰宇",
            "GOOD", "ROCK", "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天",
            "AXN", "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "大爱", "人间", "客家", "壹电视", "CTI", "CTS", "PTS", "NTV", "Fuji TV",
            "NHK", "TBS", "WOWOW", "Sky", "ESPN", "BEIN", "DAZN", "Astro",
        ],
        "其他頻道": []
    }

    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]

    MAX_SOURCES_PER_DOMAIN = 0
    WEB_SOURCES: List[str] = []       # 从 config.json 动态加载
    ALL_WEB_SOURCES: List[str] = [   # 合并预制源 + config.json 源，去重后共 ~34 个
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
        "https://live.zbds.top/tv/iptv4.m3u",
        "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8",
    ]

    UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'VLC/3.0.18 LibVLC/3.0.18',
        'Kodi/21.0 (Omega) Android/13.0.0',
        'TiviMate/4.7.0 (Android TV)',
    ]

    # ✅ 点播域名黑名单
    VOD_DOMAINS = {
        "vd2.bdstatic.com", "vd3.bdstatic.com", "vd4.bdstatic.com", "vdse.bdstatic.com",
        "www.iesdouyin.com",
        "jsmov2.a.yximgs.com", "txmov2.a.kwimgs.com", "alimov2.a.kwimgs.com",
        "cloud.video.taobao.com", "vodcdn.video.taobao.com",
        "php.jdshipin.com:2096", "r.jdshipin.com", "cdn.jdshipin.com",
        "ls.qingting.fm", "lhttp.qingting.fm",
        "mobi.kuwo.cn", "vdown.kuwo.cn", "vdown2.kuwo.cn",
        "tv.sohu.blog", "ah2.sohu.blog:8000",
        "bizcommon.alicdn.com", "lvbaiducdnct.inter.ptqy.gitv.tv",
    }

    # ✅ 直播频道名关键词
    LIVE_CHANNEL_KEYWORDS = re.compile(
        r'频道|台|卫视|影院|剧场|电影|剧集|直播|体育|音乐|新闻|综合|少儿|动漫|教育|财经|'
        r'Discovery|Channel|TV|News|Live|Sport|Music|Kids|Movie|Film|Drama|Anime'
    )

    # ✅ M3U8 Content-Type 白名单
    M3U8_CONTENT_TYPES = [
        'application/x-mpegurl', 'application/vnd.apple.mpegurl',
        'audio/mpegurl', 'audio/x-mpegurl',
    ]

    @classmethod
    def load_from_file(cls):
        if not cls.CONFIG_FILE.exists():
            return
        try:
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            for key, value in config.items():
                if key in cls.SAVEABLE_KEYS and hasattr(cls, key):
                    setattr(cls, key, value)
            # 加载 config.json 中的 web_sources
            if 'web_sources' in config and isinstance(config['web_sources'], list):
                cls.WEB_SOURCES = config['web_sources']
            print(f"✅ 加载配置文件：{cls.CONFIG_FILE}")
        except Exception as e:
            print(f"⚠️ 加载配置文件失败：{e}")

    @classmethod
    def init_compiled_rules(cls):
        for cat, keywords in cls.CATEGORY_RULES.items():
            if keywords:
                pattern = '|'.join(re.escape(kw) for kw in keywords)
                cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)


# ==================== 正则表达式预编译 ====================
class RegexPatterns:
    PRIVATE_IP = re.compile(
        r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|'
        r'::1$|fc00:|fe80:|fd[0-9a-f]{2}:|localhost|0\.0\.0\.0)',
        re.IGNORECASE
    )
    DATE_TAG      = re.compile(r'\[.*?\]|\(.*?\)|【.*?】|\{.*?\}')
    TVG_NAME      = re.compile(r'tvg-name="([^"]+)"')
    CCTV_FIND     = re.compile(r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)')
    CCTV_STANDARD = re.compile(r'CCTV\D*?(\d{1,2})\s*(\+?)', re.IGNORECASE)
    EMOJI         = re.compile(r'[\U00010000-\U0010ffff]+', re.UNICODE)
    NOISE         = re.compile(r'\(.*?\)|\[.*?\]|【.*?】|《.*?》|<.*?>|\{.*?\}')
    HIRES         = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清')
    SUFFIX        = re.compile(r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|540p|高清|超清|标清|直播|主线')
    BLANK         = re.compile(r'^[\s\-—_～•·:·]+$')


# ==================== 重试装饰器 ====================
def retry(max_attempts: int = None, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = max_attempts if max_attempts is not None else Config.RETRY_COUNT
            last_exception = None
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < attempts - 1:
                        time.sleep(delay * (backoff ** attempt))
            raise last_exception
        return wrapper
    return decorator


# ==================== URL 清理器 ====================
class URLCleaner:
    _cache: Dict[str, str] = {}
    _lock = threading.Lock()

    @staticmethod
    def get_fingerprint(url: str) -> str:
        if url in URLCleaner._cache:
            return URLCleaner._cache[url]
        parsed = urlparse(url)
        query_str = parsed.query
        if Config.REMOVE_REDUNDANT_PARAMS:
            keep = {'id', 'token', 'key', 'sign', 'auth'}
            query_dict = {k: v for k, v in parse_qs(parsed.query).items() if k.lower() in keep}
            query_str = urlencode(query_dict, doseq=True) if query_dict else ''
        fp = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_str}"
        with URLCleaner._lock:
            URLCleaner._cache[url] = fp
        return fp

    @staticmethod
    def is_valid(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https', 'rtmp', 'rtmps') and bool(parsed.netloc)
        except:
            return False

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        if not Config.FILTER_PRIVATE_IP:
            return True
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return not RegexPatterns.PRIVATE_IP.match(hostname)

    @staticmethod
    def is_ipv6(url: str) -> bool:
        """✅ 修复：检测是否为 IPv6 地址（URL 中的 IPv6 一定是 [::1] 格式）"""
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return hostname.startswith('[')


# ==================== M3U8 解析器（增强版） ====================
class M3U8Parser:
    """✅ 新增：M3U8 多码率解析（借鉴 Guovin）"""
    
    @staticmethod
    def parse_best_stream(url: str, content: Optional[str] = None) -> Tuple[str, Optional[int]]:
        """
        解析 M3U8，返回最高带宽的流地址
        返回: (最佳URL, 带宽bps 或 None)
        """
        if not M3U8_AVAILABLE or not Config.ENABLE_M3U8_PARSE:
            return url, None
        
        try:
            if content is None:
                resp = requests.get(url, timeout=5, headers={'User-Agent': random.choice(Config.UA_POOL)})
                content = resp.text
            
            m3u8_obj = m3u8.loads(content)
            
            # 如果有多个码率列表，选择最高带宽
            if m3u8_obj.playlists:
                best = max(m3u8_obj.playlists, key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
                bandwidth = best.stream_info.bandwidth if best.stream_info else None
                # 构建完整 URL
                if best.uri.startswith('http'):
                    return best.uri, bandwidth
                else:
                    base_url = url.rsplit('/', 1)[0]
                    return f"{base_url}/{best.uri}", bandwidth
            
            return url, None
        except:
            return url, None


# ==================== M3U 解析器 ====================
class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        parsed = []
        extinf_line = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF:'):
                extinf_line = line
            elif not line.startswith('#'):
                if extinf_line:
                    m = RegexPatterns.TVG_NAME.search(extinf_line)
                    name_part = m.group(1).strip() if m else extinf_line.split(',', 1)[-1].strip()
                    name_part = RegexPatterns.DATE_TAG.sub('', name_part).strip() or '未知频道'
                    parsed.append(f"{name_part},{line}")
                    extinf_line = None
        return parsed


# ==================== 测试结果缓存 ====================
class SpeedCache:
    """✅ 新增：测试结果持久化缓存"""
    _cache: Dict[str, Dict] = {}
    _loaded = False
    _lock = threading.Lock()

    @classmethod
    def load(cls):
        if cls._loaded or not Config.ENABLE_CACHE:
            return
        try:
            if Config.CACHE_FILE.exists():
                with open(Config.CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 过滤过期缓存
                now = time.time()
                expire_seconds = Config.CACHE_EXPIRE_HOURS * 3600
                for fp, item in data.items():
                    if now - item.get('timestamp', 0) < expire_seconds:
                        cls._cache[fp] = item
                print(f"✅ 加载缓存：{len(cls._cache)} 条有效记录")
        except:
            pass
        cls._loaded = True

    @classmethod
    def save(cls):
        if not Config.ENABLE_CACHE:
            return
        try:
            with open(Config.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cls._cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    @classmethod
    def get(cls, url: str) -> Optional[Dict]:
        fp = URLCleaner.get_fingerprint(url)
        return cls._cache.get(fp)

    @classmethod
    def set(cls, url: str, result: Dict):
        fp = URLCleaner.get_fingerprint(url)
        result['timestamp'] = time.time()
        cls._cache[fp] = result


# ==================== 网络源获取 ====================
class WebSourceFetcher:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.session = requests.Session()
        self.session.verify = False
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.FETCH_WORKERS * 2,
            pool_maxsize=Config.FETCH_WORKERS * 2,
            max_retries=1, pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

    def fetch(self, url: str, proxy: Optional[str] = None) -> List[str]:
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Accept': 'text/plain,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        timeout = (15, 30) if "github" in url else (10, 20)
        for attempt in range(Config.RETRY_COUNT):
            try:
                resp = self.session.get(url, headers=headers, timeout=timeout,
                                        allow_redirects=True, proxies=proxies)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or 'utf-8'
                lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
                if not lines:
                    return []
                parsed = M3UParser.parse(lines) if any(l.startswith('#EXTM3U') for l in lines[:10]) \
                         else self._parse_plain_text(lines)
                unique, seen = [], set()
                for item in parsed:
                    if ',' not in item:
                        continue
                    _, url_part = item.split(',', 1)
                    fp = URLCleaner.get_fingerprint(url_part.strip())
                    if fp not in seen:
                        seen.add(fp)
                        unique.append(item)
                return unique
            except Exception:
                if attempt < Config.RETRY_COUNT - 1:
                    time.sleep(0.5 * (2 ** attempt))
        return []

    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        parsed = []
        for line in lines:
            if ',' not in line or '://' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            if URLCleaner.is_valid(url_part.strip()):
                parsed.append(f"{name_part.strip()},{url_part.strip()}")
        return parsed


# ==================== 异步爬虫 ====================
class AsyncWebSourceCrawler:
    def __init__(self):
        self.session = None
        self.new_sources: Set[str] = set()

    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=5.0),
            limits=httpx.Limits(max_connections=30),
            verify=False, follow_redirects=True
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def crawl_all(self) -> Set[str]:
        print("🔍 开始异步爬取网络源...")
        all_sources = list(Config.ALL_WEB_SOURCES)
        for src in Config.WEB_SOURCES:
            if src not in all_sources:
                all_sources.append(src)
        print(f"📡 共 {len(all_sources)} 个源待爬取...")
        for url in all_sources:
            try:
                resp = await self.session.get(url, timeout=10.0)
                if resp.status_code == 200 and resp.text:
                    matches = re.findall(r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt)', resp.text, re.I)
                    self.new_sources.update(matches)
            except:
                pass
        print(f"✅ 爬取完成：发现新源 {len(self.new_sources)} 个")
        return self.new_sources


# ==================== 直播源检测（增强版） ====================
class StreamChecker:
    """✅ 增强：下载速度检测 + 分辨率检测 + M3U8解析"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.MAX_WORKERS * 2,
            pool_maxsize=Config.MAX_WORKERS * 2,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    # ✅ 失效重验白名单：域名/IP 命中则 ffprobe 失败后降级重试 HTTP
    # 包含：IPTV 代理网关、非标准流媒体平台
    FFPRobe_FALLBACK_DOMAINS = {
        "194.147.100.173",   # jsy/p.php IPTV 代理
        "dxjc.pp.ua",         # 龙祥、东森代理
        "goiptv.de5.net",     # 龙华等台代理
        "goiptv.de",           # 同上
        "jsy.p.php",           # IPTV 代理路径
        "zkbhj.com",           # 加密跳转代理
        "264788.xyz",         # 非标准流媒体 CDN
        "ffzy-play",          # 非标准播放器 CDN
        "ffzy-play7",         # 同上
        "live.264788",        # 同上
        "lv-cdn7.com",        # 非标准 CDN
        "ffstream",           # 非标准流
        "vip.lz-cdn7",        # 同上
        "go-iptv",            # go-iptv 代理
        "goiptv.ggff",        # go-iptv 变种
        "858.qzz.io",         # Smart.php 代理
        "858.qzz",            # 同上
        "xghqws.cn",          # 环球卫视代理
        "hkstv.tv",           # 香港卫视
        "zhibo.hkstv",        # 同上
        "smt.go-iptv",        # Smart.php 代理
        "deshitv",            # 孟加拉 DESHI TV
        "live.264788.xyz",    # 4K 频道 CDN
    }

    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        if ',' not in line:
            return {"status": "失效", "name": "未知频道", "url": line}
        try:
            name_part, url_part = line.split(',', 1)
            url = url_part.strip().rstrip('\r\n')
            name = name_part.strip()[:100]
            if not URLCleaner.is_valid(url) or not URLCleaner.filter_private_ip(url):
                return {"status": "失效", "name": name, "url": url}
            if any(kw in name for kw in Config.BLACKLIST):
                return {"status": "失效", "name": name, "url": url}

            # ✅ IPv6 优化：直接返回高速
            is_ipv6 = Config.ENABLE_IPV6_OPTIMIZE and URLCleaner.is_ipv6(url)
            if is_ipv6:
                return {
                    "status": "有效", "name": name, "url": url,
                    "lat": Config.IPV6_DEFAULT_DELAY,
                    "speed": Config.IPV6_DEFAULT_SPEED,
                    "resolution": "1920x1080",
                    "overseas": NameProcessor.is_overseas(name),
                    "quality": 100,
                    "ipv6": True
                }

            # 检查缓存
            if Config.ENABLE_CACHE:
                cached = SpeedCache.get(url)
                if cached and cached.get('valid'):
                    return {
                        "status": "有效", "name": name, "url": url,
                        "lat": cached.get('delay', 0),
                        "speed": cached.get('speed', 0),
                        "resolution": cached.get('resolution'),
                        "overseas": NameProcessor.is_overseas(name),
                        "quality": self._calc_quality(cached.get('delay', 99), cached.get('speed', 0))
                    }

            overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN

            # ✅ 命中降级白名单：跳过 ffprobe，直接 HTTP 检测（避免无谓等待）
            if self._should_fallback(url):
                result = self._check_with_http(url, name, timeout, proxy, overseas, fallback=True)
                if result.get("status") == "有效":
                    if Config.ENABLE_CACHE:
                        SpeedCache.set(url, {
                            'valid': True, 'delay': result.get('lat', 0),
                            'speed': 1.0, 'resolution': None
                        })
                return result if result else {"status": "失效", "name": name, "url": url}

            # ffprobe 检测（已合并分辨率检测）
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)

            if result and result.get("status") == "有效":
                # ✅ 分辨率过滤
                if Config.ENABLE_RESOLUTION_TEST:
                    res = result.get('resolution')
                    if res:
                        h = int(res.split('x')[1]) if 'x' in res else 0
                        if h < Config.MIN_RESOLUTION_HEIGHT:
                            result['status'] = '失效'
                            result['reason'] = f'分辨率过低({res})'
                # ✅ 速度检测
                if Config.ENABLE_SPEED_TEST and result.get('status') == '有效':
                    speed = self._test_speed(url, proxy)
                    result['speed'] = speed
                    if speed < Config.MIN_SPEED_MBPS and speed != float('inf'):
                        result['status'] = '失效'
                        result['reason'] = f'速度过低({speed:.2f}MB/s)'
                # 缓存结果
                if result.get('status') == '有效' and Config.ENABLE_CACHE:
                    SpeedCache.set(url, {
                        'valid': True, 'delay': result.get('lat', 0),
                        'speed': result.get('speed', 0), 'resolution': result.get('resolution')
                    })
                return result

            return result if result else {"status": "失效", "name": name, "url": url}
        except Exception as e:
            return {"status": "失效", "name": "未知频道", "url": line, "reason": str(e)[:30]}

    def _should_fallback(self, url: str) -> bool:
        """检测 URL 是否命中降级重验白名单（ffprobe 不友好但 HTTP 可能通的域名）"""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()
        for domain in self.FFPRobe_FALLBACK_DOMAINS:
            if domain in netloc or domain in path:
                return True
        return False

    def _check_with_ffprobe(self, url: str, name: str, timeout: int,
                            proxy: Optional[str], overseas: bool) -> Optional[Dict]:
        start = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        ua = random.choice(Config.UA_POOL)
        headers = f'User-Agent: {ua}\r\nReferer: {domain}\r\n'
        cmd = [
            'ffprobe', '-headers', headers, '-v', 'error',
            '-show_entries', 'stream=codec_type,width,height:format=duration,format_name',
            '-probesize', '5000000', '-analyzeduration', '10000000',
            '-timeout', str(int(timeout * 1_000_000)),
            '-err_detect', 'ignore_err',          # ✅ 借鉴：忽略非致命错误
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '2',  # ✅ 借鉴：支持断流重连
            '-fflags', 'nobuffer+flush_packets',  # ✅ 借鉴：低延迟模式
            '-user_agent', ua,
            '-of', 'csv=p=0',
        ]
        if proxy:
            cmd.extend(['-http_proxy', proxy])
        cmd.append(url)
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            stdout, stderr = proc.communicate(timeout=timeout + 2)
            stdout_text = stdout.decode('utf-8', errors='ignore')
            stderr_text = stderr.decode('utf-8', errors='ignore').lower()
            # ✅ 借鉴：检查 stderr 致命错误关键字
            has_fatal = any(kw in stderr_text for kw in Config.FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_text or 'codec_type=audio' in stdout_text
            if not has_fatal and has_stream:
                lat = round(time.time() - start, 2)
                result = {"status": "有效", "name": name, "url": url, "lat": lat,
                          "overseas": overseas, "quality": self._calc_quality(lat, 0)}
                # ✅ 合并分辨率检测：解析 ffprobe 输出
                parts = stdout_text.strip().split(',')
                if len(parts) >= 3 and parts[0] == 'video':
                    result['resolution'] = f"{parts[1]}x{parts[2]}"
                return result
        except Exception:
            if proc:
                try: proc.kill()
                except: pass
        return None

    def _check_with_http(self, url: str, name: str, timeout: int,
                         proxy: Optional[str], overseas: bool, fallback: bool = False) -> Dict:
        if Config.REQUEST_JITTER:
            time.sleep(random.uniform(0.05, 0.3))
        start = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        try:
            resp = self.session.head(url, headers=headers, timeout=timeout // 2,
                                     allow_redirects=True, proxies=proxies)
            if resp.status_code in (200, 206, 301, 302, 304):
                lat = round(time.time() - start, 2)
                default_speed = 1.0 if fallback else 0
                return {"status": "有效", "name": name, "url": url, "lat": lat,
                        "overseas": overseas, "quality": self._calc_quality(lat, default_speed),
                        "fallback": fallback}
            return {"status": "失效", "name": name, "url": url, "overseas": overseas,
                    "reason": f"HTTP{resp.status_code}"}
        except Exception:
            return {"status": "失效", "name": name, "url": url, "overseas": overseas,
                    "reason": "检测超时"}

    def _test_speed(self, url: str, proxy: Optional[str] = None) -> float:
        """✅ 增强：下载速度检测，含稳定性窗口（借鉴 Guovin）"""
        try:
            headers = {'User-Agent': random.choice(Config.UA_POOL)}
            proxies = {'http': proxy, 'https': proxy} if proxy else None
            
            # IPv6 优化：直接返回高速
            if Config.ENABLE_IPV6_OPTIMIZE and URLCleaner.is_ipv6(url):
                return Config.IPV6_DEFAULT_SPEED
            
            # M3U8 解析：选择最高带宽流
            best_url, bandwidth = M3U8Parser.parse_best_stream(url)
            if best_url != url:
                url = best_url
            
            start = time.time()
            resp = self.session.get(url, headers=headers, stream=True,
                                    timeout=Config.SPEED_TEST_TIMEOUT, proxies=proxies)
            
            # 稳定性检测：多次采样
            speeds = []
            total = 0
            chunk_count = 0
            
            for chunk in resp.iter_content(chunk_size=8192):
                total += len(chunk)
                chunk_count += 1
                
                # 每 8 个 chunk 记录一次速度
                if chunk_count % 8 == 0:
                    elapsed = time.time() - start
                    if elapsed > 0:
                        speeds.append(total / elapsed / 1024 / 1024)
                
                # 达到最小下载量或时间限制
                if total >= Config.SPEED_TEST_MIN_BYTES or time.time() - start >= Config.SPEED_TEST_MIN_TIME:
                    break
            
            elapsed = time.time() - start
            if elapsed <= 0:
                return 0
            
            # 稳定性检测：最后 N 次采样的波动
            if len(speeds) >= Config.STABILITY_WINDOW and speeds:
                recent = speeds[-Config.STABILITY_WINDOW:]
                avg = sum(recent) / len(recent)
                if avg > 0:
                    variance = max(abs(s - avg) / avg for s in recent)
                    if variance > Config.STABILITY_THRESHOLD:
                        # 不稳定，降低评分
                        return avg * 0.7
            
            return total / elapsed / 1024 / 1024
        except:
            return 0

    def _get_resolution(self, url: str, timeout: int) -> Optional[str]:
        """⚠️ 已废弃：分辨率检测已合并到 _check_with_ffprobe（一次 ffprobe 调用同时获取流信息和分辨率）"""
        return None  # 不再使用，保留方法签名避免外部引用报错

    @staticmethod
    def _calc_quality(latency: float, speed: float) -> int:
        """✅ 增强：综合延迟和速度评分，含 IPv6 加成"""
        # IPv6 加成：低延迟默认高分
        if speed == float('inf'):
            return 100
        
        # 延迟评分
        if latency <= 1:  lat_score = 100
        elif latency <= 3: lat_score = 80
        elif latency <= 5: lat_score = 60
        elif latency <= 10: lat_score = 40
        else: lat_score = 20
        
        # 速度评分
        if speed >= 5: spd_score = 100
        elif speed >= 2: spd_score = 80
        elif speed >= 1: spd_score = 60
        elif speed >= 0.5: spd_score = 40
        else: spd_score = 20
        
        # 综合评分（延迟权重 60%，速度权重 40%）
        return int(lat_score * 0.6 + spd_score * 0.4)


# ==================== 名称处理器 ====================
class NameProcessor:
    _simplify_cache: Dict[str, str] = {}
    _lock = threading.Lock()

    @staticmethod
    @lru_cache(maxsize=8192)
    def normalize_cctv(name: str) -> str:
        if not name:
            return name
        upper = name.upper().replace('ＣＣＴＶ', 'CCTV')
        if 'CCTV' not in upper:
            return name
        m = RegexPatterns.CCTV_STANDARD.search(upper)
        if not m:
            return name
        num = str(int(m.group(1)))
        plus = m.group(2)
        if num == '5':
            return 'CCTV5+' if (plus or '+' in upper) else 'CCTV5'
        return f'CCTV{num}'

    @staticmethod
    def simplify(text: str) -> str:
        if not text:
            return ''
        with NameProcessor._lock:
            if text in NameProcessor._simplify_cache:
                return NameProcessor._simplify_cache[text]
        result = zhconv.convert(text, 'zh-hans').strip()
        with NameProcessor._lock:
            NameProcessor._simplify_cache[text] = result
        return result

    @staticmethod
    @lru_cache(maxsize=8192)
    def clean(name: str) -> str:
        if not name or not name.strip():
            return '未知频道'
        n = RegexPatterns.EMOJI.sub('', name)
        n = RegexPatterns.NOISE.sub('', n)
        if not RegexPatterns.HIRES.search(n):
            m = RegexPatterns.CCTV_FIND.search(n)
            if m:
                return NameProcessor.normalize_cctv(m.group(1).upper())
        n = RegexPatterns.SUFFIX.sub('', n)
        n = NameProcessor.simplify(n)
        n = NameProcessor.normalize_cctv(n)
        return n.strip() if n and not RegexPatterns.BLANK.match(n) else '未知频道'

    @staticmethod
    @lru_cache(maxsize=5000)
    def is_overseas(name: str) -> bool:
        return any(kw in name.upper() for kw in Config.OVERSEAS_KEYWORDS)

    @staticmethod
    @lru_cache(maxsize=8192)
    def get_category(name: str) -> Optional[str]:
        s = NameProcessor.simplify(name)
        if any(kw in s for kw in Config.BLACKLIST):
            return None
        for cat in Config.CATEGORY_ORDER[:-1]:
            if cat in Config.CATEGORY_RULES_COMPILED:
                if Config.CATEGORY_RULES_COMPILED[cat].search(s):
                    return cat
        return '其他頻道'

    @staticmethod
    def normalize(name: str) -> str:
        return NameProcessor.clean(name)


# ==================== 主程序 ====================
class IPTVChecker:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats = {
            'total': 0, 'valid': 0, 'failed': 0,
            'by_overseas': {'cn': 0, 'overseas': 0},
            'by_category': {cat: 0 for cat in Config.CATEGORY_ORDER}
        }

    def setup_logger(self):
        self.logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def pre_check(self, input_file: Path, output_file: Path) -> bool:
        try:
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
            self.logger.info("✅ ffprobe 正常")
        except:
            self.logger.error("❌ 未安装 ffprobe")
            return False
        if not input_file.exists():
            self.logger.warning(f"⚠️ 本地文件不存在: {input_file}")
        if Config.AUTO_BACKUP and output_file.exists():
            ts = time.strftime('%Y%m%d_%H%M%S')
            backup = output_file.with_name(f"{output_file.stem}_backup_{ts}.txt")
            output_file.rename(backup)
            self.logger.info(f"📦 备份原文件: {backup.name}")
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict):
        for line in lines:
            if ',' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            url = url_part.strip().rstrip('\r\n')
            name = NameProcessor.clean(name_part.strip())
            if not name or name in ('未知频道', '爬取源'):
                continue
            if not URLCleaner.is_valid(url) or not URLCleaner.filter_private_ip(url):
                continue
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            if domain in Config.VOD_DOMAINS or parsed.netloc in Config.VOD_DOMAINS:
                if not Config.LIVE_CHANNEL_KEYWORDS.search(name):
                    continue
            fp = URLCleaner.get_fingerprint(url)
            if fp not in seen_fp:
                seen_fp.add(fp)
                domain_lines[domain].append(f"{name},{url}")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        seen_fp = pre_seen_fp if pre_seen_fp is not None else set()
        domain_lines = pre_domain_lines if pre_domain_lines is not None else defaultdict(list)
        lines_to_check: List[str] = []

        # 加载缓存
        if Config.ENABLE_CACHE:
            SpeedCache.load()

        # 读取本地文件
        input_path = args.input if args.input else Config.INPUT_FILE
        if Config.ENABLE_LOCAL_CHECK or args.input:
            self.logger.info(f"📂 读取本地文件：{input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    self.process_lines([l.strip() for l in f if l.strip()], seen_fp, domain_lines)
            except Exception as e:
                self.logger.error(f"❌ 读取失败: {e}")

        # 网络源拉取（合并 ALL_WEB_SOURCES + config.json WEB_SOURCES，去重）
        if Config.ENABLE_WEB_CHECK and not args.no_web:
            all_sources = list(Config.ALL_WEB_SOURCES)
            for src in Config.WEB_SOURCES:
                if src not in all_sources:
                    all_sources.append(src)
            self.logger.info(f"🌐 并发拉取 {len(all_sources)} 个网络源...")
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                futures = {executor.submit(self.fetcher.fetch, url, Config.PROXY): url for url in all_sources}
                for future in as_completed(futures):
                    try:
                        fetched = future.result()
                        if fetched:
                            self.process_lines(fetched, seen_fp, domain_lines)
                    except:
                        pass

        # 收集待测源
        for urls in domain_lines.values():
            lines_to_check.extend(urls if Config.MAX_SOURCES_PER_DOMAIN <= 0 else urls[:Config.MAX_SOURCES_PER_DOMAIN])

        total = len(lines_to_check)
        if total == 0:
            self.logger.warning("⚠️ 没有待测源")
            return

        self.stats['total'] = total
        cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list: List[str] = []

        self.logger.info(f"🚀 并发检测：{min(args.workers, total)} 个线程")
        with ThreadPoolExecutor(max_workers=min(args.workers, total)) as executor, \
             tqdm(total=total, desc="测活中", unit="源", ncols=80) as pbar:
            futures = [executor.submit(self.checker.check, ln, Config.PROXY) for ln in lines_to_check]
            for future in as_completed(futures):
                r = future.result()
                pbar.update(1)
                if r["status"] == "有效":
                    self.stats['valid'] += 1
                    self.stats['by_overseas']['overseas' if r.get("overseas") else 'cn'] += 1
                    cat = NameProcessor.get_category(r["name"])
                    if cat and cat in cat_map:
                        cat_map[cat].append(r)
                        self.stats['by_category'][cat] += 1
                else:
                    self.stats['failed'] += 1
                    if Config.ARCHIVE_FAIL:
                        fail_list.append(f"{r['name']},{r['url']}")
                pbar.set_postfix({"有效率": f"{self.stats['valid'] / max(pbar.n, 1) * 100:.1f}%"})

        # 保存缓存
        if Config.ENABLE_CACHE:
            SpeedCache.save()

        if Config.ARCHIVE_FAIL and fail_list:
            self.write_failures(fail_list)

        self.write_results(args.output if args.output else str(Config.OUTPUT_FILE), cat_map, total)

    async def run_async(self, args):
        Config.init_compiled_rules()
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)
        if Config.ENABLE_WEB_FETCH:
            self.logger.info("🌐 启动异步爬虫...")
            async with AsyncWebSourceCrawler() as crawler:
                new_sources = await crawler.crawl_all()
                if new_sources:
                    for url in new_sources:
                        # 用 URL 域名作频道名（避免 "爬取源" 被 process_lines 过滤）
                        parsed = urlparse(url)
                        short_domain = parsed.netloc.split(':')[0]
                        raw_lines = [f"{short_domain},{url}"]
                        self.process_lines(raw_lines, seen_fp, domain_lines)
        self.run(args, pre_seen_fp=seen_fp, pre_domain_lines=domain_lines)

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int):
        output_path = Path(output_file)
        tmp_path = output_path.with_suffix('.tmp')
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for cat in Config.CATEGORY_ORDER:
                    channels = cat_map.get(cat, [])
                    if not channels:
                        continue
                    f.write(f"{cat},#genre#\n")
                    channels.sort(key=lambda x: x.get('quality', 0), reverse=True)
                    grouped: Dict[str, List[Dict]] = defaultdict(list)
                    for ch in channels:
                        # ✅ 降级源(fallback)跳过质量过滤（无 ffprobe 数据，quality 分低）
                        is_fallback = ch.get('fallback')
                        if Config.ENABLE_QUALITY_FILTER and not is_fallback:
                            if ch.get('quality', 0) < Config.MIN_QUALITY_SCORE:
                                continue
                        name = NameProcessor.normalize(ch['name'])
                        if len(grouped[name]) < Config.MAX_LINKS_PER_NAME:
                            grouped[name].append(ch)

                    if cat == "央衛頻道":
                        cctv_ch = {n: i for n, i in grouped.items() if n.startswith('CCTV')}
                        other_ch = {n: i for n, i in grouped.items() if not n.startswith('CCTV')}
                        for num in range(1, 18):
                            if f'CCTV{num}' in cctv_ch:
                                for ch in sorted(cctv_ch[f'CCTV{num}'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                    f.write(f"{ch['name']},{ch['url']}\n")
                        if 'CCTV5+' in cctv_ch:
                            for ch in sorted(cctv_ch['CCTV5+'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{ch['name']},{ch['url']}\n")
                        for name in sorted(other_ch.keys(), key=lambda n: max(c.get('quality', 0) for c in other_ch[n]), reverse=True):
                            for ch in sorted(other_ch[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{name},{ch['url']}\n")
                    else:
                        for name in sorted(grouped.keys(), key=lambda n: max(c.get('quality', 0) for c in grouped[n]), reverse=True):
                            for ch in sorted(grouped[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{name},{ch['url']}\n")
                    f.write("\n")
            tmp_path.replace(output_path)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise e

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: {total} 条 | 有效: {self.stats['valid']} ({self.stats['valid']/max(total,1)*100:.1f}%)")
        self.logger.info(f"📊 境内: {self.stats['by_overseas']['cn']} | 境外: {self.stats['by_overseas']['overseas']}")
        self.logger.info(f"📁 结果: {output_path}")
        self.logger.info(f"{'='*60}")

        # 写入统计文件
        try:
            stats = {
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "total": self.stats['total'],
                "valid": self.stats['valid'],
                "failed": self.stats['failed'],
                "valid_rate": f"{self.stats['valid'] / max(self.stats['total'], 1) * 100:.1f}%",
                "by_overseas": self.stats['by_overseas'],
                "by_category": self.stats['by_category'],
            }
            with open(Config.STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            self.logger.info(f"📊 统计: {Config.STATS_FILE}")
        except:
            pass

    def write_failures(self, fail_list: List[str]):
        fail_path = Config.BASE_DIR / "live_fail.txt"
        tmp_path = fail_path.with_suffix('.tmp')
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(fail_list))
            tmp_path.replace(fail_path)
            self.logger.info(f"📁 失效源: {fail_path} ({len(fail_list)}条)")
        except:
            if tmp_path.exists():
                tmp_path.unlink()


# ==================== 仅去重模式 ====================
def dedup_only(input_file: str):
    Config.init_compiled_rules()
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_file}")
        return

    seen_fp: Set[str] = set()
    domain_lines: Dict[str, List[str]] = defaultdict(list)
    total_lines = 0
    black_count = 0

    for enc in ['utf-8', 'utf-8-sig', 'gbk']:
        try:
            content = input_path.read_text(encoding=enc)
            break
        except:
            continue

    if not content:
        print("❌ 无法读取文件")
        return

    for line in content.splitlines():
        total_lines += 1
        line = line.strip()
        if not line or ',' not in line:
            continue
        name_part, url_part = line.split(',', 1)
        name = NameProcessor.clean(name_part.strip())
        if not name or name in ('未知频道', '爬取源'):
            continue
        if any(kw in name for kw in Config.BLACKLIST):
            black_count += 1
            continue
        if not URLCleaner.is_valid(url_part.strip()):
            continue
        fp = URLCleaner.get_fingerprint(url_part.strip())
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        parsed = urlparse(url_part.strip())
        domain = f"{parsed.scheme}://{parsed.netloc}"
        domain_lines[domain].append(f"{name},{url_part.strip()}")

    cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
    for urls in domain_lines.values():
        for ln in urls:
            if ',' not in ln:
                continue
            n, u = ln.split(',', 1)
            cat = NameProcessor.get_category(n)
            if cat:
                cat_map[cat].append({"name": n, "url": u, "quality": 100, "fallback": False})

    output_path = Config.BASE_DIR / "live_ok.txt"
    tmp_path = output_path.with_suffix('.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        for cat in Config.CATEGORY_ORDER:
            channels = cat_map.get(cat, [])
            if not channels:
                continue
            f.write(f"{cat},#genre#\n")
            grouped: Dict[str, List[Dict]] = defaultdict(list)
            for ch in channels:
                name = NameProcessor.normalize(ch['name'])
                if len(grouped[name]) < Config.MAX_LINKS_PER_NAME:
                    grouped[name].append(ch)
            for name in sorted(grouped.keys()):
                for ch in sorted(grouped[name], key=lambda x: -x.get('quality', 0)):
                    f.write(f"{ch['name']},{ch['url']}\n")
            f.write("\n")
    tmp_path.replace(output_path)

    valid_count = sum(len(v) for v in domain_lines.values())
    print(f"\n{'='*50}")
    print(f"🚀 去重完成！")
    print(f"📊 原始行数: {total_lines}")
    print(f"🚫 黑名单过滤: {black_count}")
    print(f"✅ 有效 URL: {valid_count}")
    print(f"📁 结果: {output_path}")
    print(f"{'='*50}")


# ==================== 命令行入口 ====================
def main():
    Config.init_compiled_rules()
    Config.load_from_file()

    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 (Apex v2)')
    parser.add_argument('-i', '--input', default=None, help='输入文件')
    parser.add_argument('-o', '--output', default=None, help='输出文件')
    parser.add_argument('-w', '--workers', type=int, default=80, help='并发数')
    parser.add_argument('-t', '--timeout', type=int, default=8, help='超时(秒)')
    parser.add_argument('--no-web', action='store_true', help='跳过网络源')
    parser.add_argument('--proxy', default=None, help='代理')
    parser.add_argument('--async-crawl', action='store_true', help='异步爬虫')
    parser.add_argument('--dedup-only', default=None, metavar='FILE',
                        help='仅去重模式：对指定文件去重后输出到 live_ok.txt（不检测）')
    args = parser.parse_args()

    if args.dedup_only:
        dedup_only(args.dedup_only)
        sys.exit(0)

    if args.timeout:
        Config.TIMEOUT_CN = args.timeout
        Config.TIMEOUT_OVERSEAS = args.timeout * 2
    if args.workers:
        Config.MAX_WORKERS = args.workers

    checker = IPTVChecker()
    checker.setup_logger()

    print(f"{'='*60}\n🔍 环境预检...")
    if not checker.pre_check(Path(args.input) if args.input else Config.INPUT_FILE,
                             Path(args.output) if args.output else Config.OUTPUT_FILE):
        sys.exit(1)
    print(f"{'='*60}\n")

    try:
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            asyncio.run(checker.run_async(args))
        else:
            checker.run(args)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(1)


if __name__ == '__main__':
    main()
