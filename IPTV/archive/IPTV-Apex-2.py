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


# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE  = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    CONFIG_FILE = BASE_DIR / "config.json"

    ENABLE_WEB_FETCH    = False  # 异步爬虫：主动扫描网络新源
    ENABLE_WEB_CHECK    = False  # 网络拉取：检测预设源列表
    ENABLE_LOCAL_CHECK  = True   # 本地检测：读取输入文件测活

    DEBUG_MODE          = False
    AUTO_BACKUP         = True
    ARCHIVE_FAIL        = True
    MAX_WORKERS         = 80
    FETCH_WORKERS       = 8
    TIMEOUT_CN          = 8
    TIMEOUT_OVERSEAS    = 15
    RETRY_COUNT         = 2
    MAX_LINKS_PER_NAME  = 3
    FILTER_PRIVATE_IP   = True
    REMOVE_REDUNDANT_PARAMS = False
    ENABLE_QUALITY_FILTER   = True
    MIN_QUALITY_SCORE       = 80
    PROXY = None

    # 下载测速配置
    SPEED_TEST_ENABLED  = True   # 启用下载测速
    SPEED_TEST_BYTES    = 65536  # 测速下载字节数（64KB）

    SAVEABLE_KEYS = {
        'ENABLE_WEB_FETCH', 'ENABLE_WEB_CHECK', 'ENABLE_LOCAL_CHECK',
        'DEBUG_MODE', 'AUTO_BACKUP', 'ARCHIVE_FAIL',
        'MAX_WORKERS', 'FETCH_WORKERS', 'TIMEOUT_CN', 'TIMEOUT_OVERSEAS',
        'RETRY_COUNT', 'MAX_LINKS_PER_NAME',
        'FILTER_PRIVATE_IP', 'REMOVE_REDUNDANT_PARAMS',
        'ENABLE_QUALITY_FILTER', 'MIN_QUALITY_SCORE', 'PROXY',
        'SPEED_TEST_ENABLED', 'SPEED_TEST_BYTES',
        'MAX_SOURCES_PER_DOMAIN', 'WEB_SOURCES',
    }

    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示",
        "教程", "联系", "推广", "免费"
    }

    # ✅ 境外频道关键词（仅用于超时判断，不参与分类）
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "Discovery", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "beIN",
    }

    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
    }

    CATEGORY_RULES_COMPILED: Dict = {}

    # ✅ 分类规则优化：去重、明确归属、补充港澳台关键词
    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "F1", "MotoGP",
            "WWE", "UFC", "拳击", "高尔夫", "GOLF", "ATP", "WTA", "斯诺克",
            "奥运", "亚运", "世界杯", "欧洲杯", "美洲杯", "亚洲杯", "CBA",
        ],
        "音樂頻道": [
            "音乐", "演唱会", "MTV", "CMUSIC", "KTV", "流行", "嘻哈", "摇滚",
            "古典", "爵士", "民谣", "电音", "EDM", "Karaoke", "Channel V",
            "Trace", "VH1", "MTV Hits", "MTV Live", "KKBOX", "KAYOPOPS",
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼", "宝宝", "宝贝",
            "炫动", "CARTOON", "ANIME", "ANIMATION", "KIDS", "CHILDREN",
            "NICK", "DISNEY", "TOON", "BOOMERANG", "尼克", "小公视", "蓝猫",
            "喜羊羊", "熊出没",
        ],
        "影視劇集": [
            "爱奇艺", "优酷", "腾讯视频", "芒果TV", "IQIYI", "POPC", "剧集",
            "电影", "影院", "影视", "剧场", "Hallmark", "龙华", "Prime",
            "Paramount+", "电视剧", "Peacock", "Max", "靖洋", "Showtime",
            "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime", "华纳",
            "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
            "Marvel", "DCU", "Star Wars", "NETFLIX", "SERIES", "MOVIE",
            "网剧", "短剧", "微剧", "首播", "独播", "热播", "天映", "港片",
            "台剧", "韩剧", "日剧", "美剧", "英剧", "HBO", "悬疑", "科幻",
            "古装", "都市", "喜剧", "爱情", "冒险", "制片", "影业", "院线",
            "怀旧", "经典", "邵氏", "华剧", "华影", "金鹰", "星河", "新视觉",
        ],
        "港澳台頻": [
            # ✅ 港澳台本土频道（去除与影视频道重复的 HBO、NETFLIX 等）
            "翡翠", "博斯", "凤凰", "TVB", "明珠", "八度", "华艺", "环球",
            "生命", "镜", "澳", "台湾", "探索", "年代", "唯心", "公视",
            "东森", "三立", "爱尔达", "NOW", "VIU", "STAR", "星空", "纬来",
            "非凡", "中天", "中视", "无线", "寰宇", "Z频道", "GOOD", "ROCK",
            "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天", "AXN",
            "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "大爱", "人间", "客家", "壹电视", "CTI", "CTS", "PTS", "NTV",
            "Fuji TV", "TBS", "WOWOW", "Sky", "DAZN", "Eleven Sports",
            "TrueVisions", "Astro", "Unifi TV", "HyppTV", "myTV SUPER",
            "Now TV", "Cable TV", "PCCW", "HKTV", "Disney+", "RHK", "TTV",
            "FTV", "TRANSTV", "TLC", "SURIA", "SUPERFREE", "SUNTV", "SUNEWS",
            "SUMUSIC", "SULIF", "SUKART", "SPOT2", "SPOT", "SONYTEN3", "SET新闻",
            "RTV", "ROCKACTION", "RIA", "QJ", "OKEY", "NET", "MTLIVE", "猪王",
            "华仁", "宏达", "卫视中文", "卫视电影", "卫视音乐",
        ],
        "其他頻道": []
    }

    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]

    MAX_SOURCES_PER_DOMAIN = 0

    PRESET_FILES = [
        "https://live.zbds.top/tv/iptv4.m3u",
        "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8",
        "https://raw.githubusercontent.com/MichaelJorky/Free-IPTV-M3U-Playlist/main/iptv-hongkong.m3u",
        "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
        "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt",
        "http://txt.gt.tc/users/HKTV.txt",
        "https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt",
        "https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u",
        "https://raw.githubusercontent.com/FGBLH/FG/refs/heads/main/%E6%B8%AF%E5%8F%B0%E5%A4%A7%E9%99%86",
        "https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt",
        "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
        "http://tv123.vvvv.ee/tv.m3u",
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
        "http://47.120.41.246:8899/xinzb.txt",
        "http://iptv.4666888.xyz/FYTV.m3u",
        "https://raw.githubusercontent.com/judy-gotv/iptv/main/litv.m3u",
        "https://live.hacks.tools/iptv/languages/zho.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/macau.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/%E7%94%B5%E5%BD%B1%E9%A2%91%E9%81%93.m3u",
        "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1"
    ]

    UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'VLC/3.0.18 LibVLC/3.0.18 (LGPLv2.1+)',
        'IINA/1.3.3 (Macintosh; Intel Mac OS X 14.5.0)',
        'PotPlayer/230502 (Windows NT 10.0; x64)',
        'Kodi/21.0 (Omega) Android/13.0.0 Sys_CPU/aarch64',
        'TiviMate/4.7.0 (Android TV)',
        'Perfect Player/1.6.0.1 (Linux;Android 13)',
        'Mozilla/5.0 (Linux; Android 13; TV Box) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Amlogic S905X4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    ]

    @classmethod
    def load_from_file(cls):
        if not cls.CONFIG_FILE.exists():
            return
        try:
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            loaded = []
            for key in cls.SAVEABLE_KEYS:
                if key in config and hasattr(cls, key):
                    setattr(cls, key, config[key])
                    loaded.append(key)
            if loaded:
                loaded_str = ' | '.join(f"{k}={getattr(cls, k)}" for k in sorted(loaded)
                                         if not isinstance(getattr(cls, k), (list, dict)))
                print(f"✅ 加载配置文件：{cls.CONFIG_FILE}（{len(loaded)}项）{loaded_str}")
        except Exception as e:
            print(f"⚠️ 加载配置文件失败：{e}，使用默认配置")

    @classmethod
    def save_to_file(cls, web_sources: List[str]):
        try:
            existing: Dict = {}
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            existing['WEB_SOURCES'] = web_sources
            existing['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"✅ 保存成功的网页源到配置文件：{cls.CONFIG_FILE}")
        except Exception as e:
            print(f"⚠️ 保存配置文件失败：{e}")

    @classmethod
    def init_compiled_rules(cls):
        for cat, keywords in cls.CATEGORY_RULES.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)


# ==================== 正则表达式预编译 ====================
class RegexPatterns:
    PRIVATE_IP = re.compile(
        r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|'
        r'::1$|fc00:|fe80:|fd[0-9a-f]{2}:|localhost|0\.0\.0\.0)',
        re.IGNORECASE
    )
    DATE_TAG      = re.compile(r'\[.*?\]|\(.*?\)|【.*?】|\{.*?\}', re.IGNORECASE)
    TVG_NAME      = re.compile(r'tvg-name="([^"]+)"')
    CCTV_FIND     = re.compile(r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)')
    CCTV_STANDARD = re.compile(r'CCTV\D*?(\d{1,2})\s*(\+?)', re.IGNORECASE)
    EMOJI         = re.compile(
        r'[\U00010000-\U0010ffff\U00002600-\U000027ff\U0000f600-\U0000f6ff'
        r'\U0000f300-\U0000f3ff\U00002300-\U000023ff\U00002500-\U000025ff'
        r'\U00002100-\U000021ff\U000000a9\U000000ae\U00002000-\U0000206f'
        r'\U00002460-\U000024ff\U00001f00-\U00001fff]+',
        re.UNICODE
    )
    NOISE         = re.compile(r'\(.*?\)|\)|\[.*?\]|【.*?】|《.*?》|<.*?>|\{.*?\}')
    HIRES         = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清')
    SUFFIX        = re.compile(
        r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|540p|高清|超清|超高清|标清|直播|主线'
    )
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
    @staticmethod
    @lru_cache(maxsize=10000)
    def get_fingerprint(url: str) -> str:
        parsed = urlparse(url)
        if Config.REMOVE_REDUNDANT_PARAMS:
            keep_params = {'id', 'token', 'key', 'sign', 'auth'}
            query_dict = {k: v for k, v in parse_qs(parsed.query).items()
                          if k.lower() in keep_params}
            query_str = urlencode(query_dict, doseq=True) if query_dict else ''
        else:
            query_str = parsed.query
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_str}"

    @staticmethod
    def is_valid(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https', 'rtmp', 'rtmps') and bool(parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        if not Config.FILTER_PRIVATE_IP:
            return True
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return not RegexPatterns.PRIVATE_IP.match(hostname)


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
                    if m:
                        name_part = m.group(1).strip()
                    else:
                        name_part = extinf_line.split(',', 1)[-1].strip()
                    name_part = RegexPatterns.DATE_TAG.sub('', name_part).strip() or '未知频道'
                    parsed.append(f"{name_part},{line}")
                    extinf_line = None
        return parsed


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
            max_retries=1,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')

    @retry(max_attempts=2, delay=0.5, backoff=2)
    def fetch(self, url: str, proxy: Optional[str] = None) -> List[str]:
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Accept': 'text/plain,text/html,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Referer': 'https://www.baidu.com',
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        timeout = (15, 30) if "githubusercontent" in url else (10, 20)
        try:
            resp = self.session.get(url, headers=headers, timeout=timeout,
                                    allow_redirects=True, proxies=proxies, stream=False)
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
        except Exception as e:
            if Config.DEBUG_MODE:
                print(f"⚠️ 拉取异常 {url}: {e}")
            return []

    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        parsed = []
        for line in lines:
            if ',' not in line or '://' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            url_part = url_part.strip()
            if URLCleaner.is_valid(url_part):
                parsed.append(f"{name_part.strip()},{url_part}")
        return parsed


# ==================== 异步爬虫 ====================
class AsyncWebSourceCrawler:
    """异步爬虫 - 多源聚合爬取"""

    # ✅ 扩展爬取源列表（30个高质量源）
    SOURCE_SITES = [
        # GitHub 主流仓库
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8",
        "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
        # iptv-org 组织源
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
        "https://iptv-org.github.io/iptv/countries/mo.m3u",
        "https://iptv-org.github.io/iptv/languages/zho.m3u",
        "https://iptv-org.github.io/iptv/index.m3u",
        # live.hacks.tools 系列
        "https://live.hacks.tools/iptv/languages/zho.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/macau.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u",
        # 国内聚合源
        "https://live.zbds.top/tv/iptv4.m3u",
        "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
        "http://47.120.41.246:8899/xinzb.txt",
        "http://iptv.4666888.xyz/FYTV.m3u",
        # 其他优质源
        "https://raw.githubusercontent.com/judy-gotv/iptv/main/litv.m3u",
        "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
        "https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1",
        "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
        "https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u",
        "https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt",
        "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt",
        "http://txt.gt.tc/users/HKTV.txt",
        "https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt",
    ]

    URL_PATTERNS = [
        r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt)[^\s<>"\']*',
        r'https?://[^\s<>"\']+/live[^\s<>"\']*',
        r'https?://[^\s<>"\']+/stream[^\s<>"\']*',
        r'https?://[^\s<>"\']+/tv[^\s<>"\']*',
        r'https?://[^\s<>"\']+:\d{4,5}[^\s<>"\']*',
    ]

    def __init__(self):
        self.session = None
        self.new_sources: Set[str] = set()
        self.all_extracted_urls: Set[str] = set()

    async def __aenter__(self):
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=30, max_connections=50, keepalive_expiry=20.0)
        self.session = httpx.AsyncClient(timeout=timeout, limits=limits, verify=False, follow_redirects=True)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 2.0) -> bool:
        """快速验证 URL 可达性"""
        try:
            resp = await self.session.head(url, timeout=timeout, follow_redirects=True)
            return resp.status_code in (200, 206, 301, 302)
        except Exception:
            return False

    async def get_speed_with_download(self, url: str, timeout: float = 5.0, min_bytes: int = 65536) -> float:
        """✅ 下载前 N KB 数据计算真实速度（返回 MB/s）"""
        if not Config.SPEED_TEST_ENABLED:
            return 0.0
        try:
            start = time.time()
            async with self.session.stream('GET', url, timeout=timeout, follow_redirects=True) as resp:
                if resp.status_code not in (200, 206):
                    return 0.0
                downloaded = 0
                async for chunk in resp.aiter_bytes(8192):
                    downloaded += len(chunk)
                    if downloaded >= min_bytes:
                        break
            elapsed = time.time() - start
            if elapsed <= 0:
                return 0.0
            speed_mbps = (downloaded / elapsed) / (1024 * 1024)  # MB/s
            return round(speed_mbps, 2)
        except Exception:
            return 0.0

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        """从内容中提取有效源 URL"""
        if depth > 1:
            return set()
        try:
            resp = await self.session.get(url, timeout=10.0)
            if resp.status_code != 200 or not resp.text or len(resp.text) < 10:
                return set()
            all_matches: Set[str] = set()
            for pattern in self.URL_PATTERNS:
                all_matches.update(re.findall(pattern, resp.text, re.IGNORECASE))
            valid_sources: Set[str] = set()
            semaphore = asyncio.Semaphore(40)  # ✅ 提高并发验证数

            async def validate_and_add(source: str):
                if len(source) < 15 or len(source) > 500:
                    return
                if any(x in source.lower() for x in ['javascript:', 'data:', 'about:', 'void(']):
                    return
                if source in self.all_extracted_urls:
                    return
                try:
                    async with semaphore:
                        if await self.quick_validate(source, timeout=2.0):
                            valid_sources.add(source)
                            self.all_extracted_urls.add(source)
                except Exception:
                    pass

            # ✅ 批量并发验证（100个一批）
            batch_size = 100
            all_list = list(all_matches)
            for i in range(0, len(all_list), batch_size):
                await asyncio.gather(*[validate_and_add(s) for s in all_list[i:i+batch_size]],
                                     return_exceptions=True)
            # 递归提取一层
            if depth < 1 and valid_sources:
                for src in list(valid_sources)[:15]:  # ✅ 增加递归上限
                    if src.endswith(('.m3u', '.m3u8', '.txt')):
                        try:
                            valid_sources.update(await self.extract_sources_from_content(src, depth + 1))
                        except Exception:
                            pass
            return valid_sources
        except Exception:
            return set()

    async def crawl_single_source(self, url: str, semaphore: asyncio.Semaphore) -> Tuple[str, Set[str]]:
        """爬取单个源站点"""
        async with semaphore:
            try:
                if not await self.quick_validate(url, timeout=3.0):
                    return (url, set())
                extracted = await self.extract_sources_from_content(url)
                if extracted:
                    self.new_sources.update(extracted)
                return (url, extracted)
            except Exception:
                return (url, set())

    async def crawl_all_with_validation(self, validator_func) -> Dict[str, Tuple[str, float]]:
        """✅ 爬取并验证新源，返回 {url: (name, speed_mbps)}"""
        print("🔍 开始异步爬取网络源...")
        print(f"📋 待爬取源数: {len(self.SOURCE_SITES)} 个")
        semaphore = asyncio.Semaphore(15)  # ✅ 提高并发数
        tasks = [self.crawl_single_source(url, semaphore) for url in self.SOURCE_SITES]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            await coro
            completed += 1
            if completed % 5 == 0 or completed == len(self.SOURCE_SITES):
                print(f"🔄 进度: {completed}/{len(self.SOURCE_SITES)} 个源已处理")
        print(f"✅ 爬取完成: 发现新源 {len(self.new_sources)} 个")

        # ✅ 并发验证新源 + 测速
        if not self.new_sources:
            return {}
        print(f"🔍 开始验证新源并测速...")
        validated: Dict[str, Tuple[str, float]] = {}
        speed_sem = asyncio.Semaphore(30)

        async def validate_one(src_url: str) -> Optional[Tuple[str, str, float]]:
            async with speed_sem:
                try:
                    # 测速
                    speed = await self.get_speed_with_download(src_url, timeout=5.0)
                    if speed > 0:
                        # 用域名作为频道名
                        domain = urlparse(src_url).netloc.split(':')[0]
                        return (src_url, domain, speed)
                except Exception:
                    pass
            return None

        results = await asyncio.gather(*[validate_one(u) for u in self.new_sources], return_exceptions=True)
        for r in results:
            if isinstance(r, tuple) and len(r) == 3:
                validated[r[0]] = (r[1], r[2])

        print(f"✅ 新源验证完成: {len(validated)}/{len(self.new_sources)} 个有效")
        return validated


# ==================== 直播源检测 ====================
class StreamChecker:
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
        self