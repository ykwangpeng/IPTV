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
    INPUT_FILE = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    CONFIG_FILE = BASE_DIR / "config.json"
    
    ENABLE_WEB_FETCH = False           # 是否启用自动爬取新增网络直播源的功能
    ENABLE_WEB_CHECK = False           # 是否启用拉取并检测预设网络源的功能
    ENABLE_LOCAL_CHECK = True         # 是否启用读取并检测本地输入文件的功能
        
    DEBUG_MODE = False                # 调试模式开关
    AUTO_BACKUP = True                # 自动备份开关
    ARCHIVE_FAIL = True               # 失效源归档开关
    MAX_WORKERS = 80                  # 直播源检测的最大并发线程数
    FETCH_WORKERS = 8                 # 网络源拉取的最大并发线程数
    TIMEOUT_CN = 8                    # 境内直播源检测超时时间（秒）
    TIMEOUT_OVERSEAS = 15             # 境外直播源检测超时时间（秒）
    RETRY_COUNT = 2                   # 网络请求重试次数
    REQUEST_JITTER = False            # 请求抖动开关
    MAX_LINKS_PER_NAME = 3            # 每个频道保留的最大有效链接数
    FILTER_PRIVATE_IP = True          # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False   # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER = True      # 质量过滤开关
    MIN_QUALITY_SCORE = 80            # 最低质量评分阈值
    PROXY = None                      # 请求使用代理配置

    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", 
        "教程", "联系", "推广", "免费"
    }
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
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

    CATEGORY_RULES_COMPILED = {}

    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "咪咕", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J 联赛", "K 联赛", "美职",
            "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
            "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运", "文体",
            "亚运", "世界杯", "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA", "五大联赛", "Pac-12"
        ],
        "音樂頻道": [
            "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV",
            "流行", "嘻哈", "摇滚", "古典", "爵士", "民谣", "电音", "EDM",
            "纯音乐", "伴奏", "Karaoke", "Channel V", "Trace", "VH1", "MTV Hits",
            "MTV Live", "KKBOX", "女团", "Space Shower", "KAYOPOPS", "Musicon"
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼", "宝宝", "宝贝",
            "炫动", "卡通片", "动漫片", "动画片", "CARTOON", "ANIME", "ANIMATION",
            "KIDS", "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS",
            "TOON", "BOOMERANG", "尼克", "小公视", "蓝猫", "喜羊羊", "熊出没"
        ],
        "影視劇集": [
            "爱奇艺", "优酷", "腾讯视频", "芒果 TV", "IQIYI", "POPC", 
            "剧集", "电影", "影院", "影视", "剧场", "Hallmark", "龙华",
            "Prime", "Paramount+", "电视剧", "Peacock", "Max", "靖洋",
            "Showtime", "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime",
            "华纳", "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
            "Marvel", "DCU", "Star Wars", "NETFLIX", "SERIES", "MOVIE", "SHORTS",
            "网剧", "短剧", "微剧", "首播", "独播", "热播", "天映",
            "港片", "台剧", "韩剧", "日剧", "美剧", "英剧", "HBO",
            "悬疑", "科幻", "古装", "都市", "喜剧", "爱情", "冒险",
            "制片", "影业", "院线", "怀旧", "经典", "邵氏", "华剧", 
            "华影", "金鹰", "星河", "新视觉"
        ],
        "港澳台頻": [
            "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理",
            "香港", "华文", "八度", "华艺", "环球", "生命", "镜", "澳", "台湾", "探索",
            "年代", "明珠", "唯心", "公视", "东森", "三立", "爱尔达", "NOW", "VIU",
            "STAR", "星空", "纬来", "非凡", "中天", "中视", "无线", "寰宇",
            "GOOD", "ROCK", "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天",
            "AXN", "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "大爱", "人间", "客家", "壹电视", "CTI", "CTS", "PTS", "NTV", "Fuji TV",
            "NHK", "TBS", "WOWOW", "Sky", "ESPN", "beIN", "DAZN", "Eleven Sports",
            "SPOTV NOW", "TrueVisions", "Astro", "Unifi TV", "HyppTV", "myTV SUPER",
            "Now TV", "Cable TV", "PCCW", "HKTV", "Viu", "Netflix", "Disney+",
            "TTV", "FTV", "TRANSTV", "TLC", "SURIA", "SUPERFREE", "SUNTV", "SUNEWS",
            "SUMUSIC", "SULIF", "SUKART", "SPOT2", "SPOT", "SONYTEN3", "SET 新闻",
            "RTV", "ROCKACTION", "RIA", "QJ", "OKEY", "NET", "MTLIVE", "猪王", "华仁",
            "华视", "台视", "民视", "八大", "东森", "三立", "中天", "TVBS", "壹电视",
            "客家", "公视", "宏达", "卫视", "卫视中文", "卫视电影", "卫视音乐", "凤凰"
        ],
        "其他頻道": []
    }

    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]

    # 每个域名最多保留的源数量（0表示不限制）
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
    ]

    @classmethod
    def load_from_file(cls):
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for key, value in config.items():
                    if hasattr(cls, key) and key != 'web_sources':
                        setattr(cls, key, value)
                print(f"✅ 加载配置文件：{cls.CONFIG_FILE}")
            except Exception as e:
                print(f"⚠️ 加载配置文件失败：{e}, 使用默认配置")

    @classmethod
    def save_to_file(cls, web_sources):
        """保存成功的网页源到配置文件"""
        try:
            existing_config = {}
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    existing_config = json.load(f)

            existing_config['web_sources'] = web_sources
            existing_config['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')

            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, ensure_ascii=False, indent=2)
            print(f"✅ 保存成功的网页源到配置文件：{cls.CONFIG_FILE}")
        except Exception as e:
            print(f"⚠️ 保存配置文件失败：{e}")

    @classmethod
    def init_compiled_rules(cls):
        """初始化时编译正则表达式"""
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
    # CCTV 专用（借鉴 IPTV-7）
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
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        time.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator


# ==================== URL 清理器 ====================
class URLCleaner:
    @staticmethod
    @lru_cache(maxsize=10000)
    def get_fingerprint(url: str) -> str:
        """URL指纹提取，带缓存"""
        parsed = urlparse(url)
        if Config.REMOVE_REDUNDANT_PARAMS:
            keep_params = {'id', 'token', 'key', 'sign', 'auth'}
            query_dict = {k: v for k, v in parse_qs(parsed.query).items() 
                         if k.lower() in keep_params}
            query_str = urlencode(query_dict, doseq=True) if query_dict else ''
        else:
            query_str = parsed.query
        fingerprint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_str}"
        return fingerprint

    @staticmethod
    def is_valid(url: str) -> bool:
        """URL有效性检查"""
        try:
            parsed = urlparse(url)
            return all([parsed.scheme in ('http', 'https', 'rtmp', 'rtmps'), 
                       parsed.netloc])
        except Exception:
            return False

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        """内网IP过滤"""
        parsed = urlparse(url)
        if not Config.FILTER_PRIVATE_IP:
            return True
        netloc = parsed.netloc.split('@')[-1]
        hostname = netloc.split(':')[0]
        return not RegexPatterns.PRIVATE_IP.match(hostname)


# ==================== M3U 解析器 ====================
class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        """M3U文件解析"""
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
                    name_part = extinf_line.split(',', 1)[-1].strip()
                    name_part = RegexPatterns.DATE_TAG.sub('', name_part).strip() or '未知频道'
                    parsed.append(f"{name_part},{line}")
                    extinf_line = None
        
        return parsed


# ==================== 网络源获取 ====================
class WebSourceFetcher:
    """网络源获取器 - 连接池复用"""
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
        """网络源拉取"""
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
            
            if any(l.startswith('#EXTM3U') for l in lines[:10]):
                parsed = M3UParser.parse(lines)
            else:
                parsed = self._parse_plain_text(lines)
            
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
    
    # 扩展爬取源列表（包含更多优质源）
    SOURCE_SITES = [
        # GitHub 热门源
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8",
        "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
        # iptv-org 多地区源
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
        "https://iptv-org.github.io/iptv/countries/mo.m3u",
        "https://iptv-org.github.io/iptv/languages/zho.m3u",
        "https://iptv-org.github.io/iptv/index.m3u",
        # 其他优质源
        "https://live.zbds.top/tv/iptv4.m3u",
        "https://live.hacks.tools/iptv/languages/zho.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/macau.m3u",
        "https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u",
    ]
    
    # 从源内容中提取链接的正则模式（扩展）
    URL_PATTERNS = [
        r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt)[^\s<>"\']*',  # 标准 m3u/m3u8/txt 链接
        r'https?://[^\s<>"\']+/live[^\s<>"\']*',  # live 路径
        r'https?://[^\s<>"\']+/stream[^\s<>"\']*',  # stream 路径
        r'https?://[^\s<>"\']+/tv[^\s<>"\']*',  # tv 路径
        r'https?://[^\s<>"\']+:\d{4,5}[^\s<>"\']*',  # 带端口的链接
    ]

    def __init__(self):
        self.session = None
        self.new_sources = set()
        self.all_extracted_urls = set()  # 去重用

    async def __aenter__(self):
        timeout = httpx.Timeout(8.0, connect=5.0)  # 降低超时避免卡住
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=30,
            keepalive_expiry=15.0
        )
        self.session = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            verify=False,
            follow_redirects=True
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 1.5) -> bool:
        """快速验证源是否有效（优化超时控制）"""
        try:
            resp = await self.session.head(url, timeout=timeout, follow_redirects=True)
            return resp.status_code in (200, 206, 301, 302)
        except Exception:
            return False

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        """从内容中提取更多源（支持递归深度）"""
        if depth > 1:  # 限制递归深度
            return set()
            
        try:
            resp = await self.session.get(url, timeout=8.0)
            if resp.status_code != 200:
                return set()
            
            text = resp.text
            if not text or len(text) < 10:
                return set()
            
            # 使用多个正则模式提取链接
            all_matches = set()
            for pattern in self.URL_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                all_matches.update(matches)
            
            # 去重并过滤
            valid_sources = set()
            semaphore = asyncio.Semaphore(30)  # 增加并发
            
            async def validate_and_add(source: str):
                # 快速过滤无效链接
                if len(source) < 15 or len(source) > 500:
                    return
                if any(x in source.lower() for x in ['javascript:', 'data:', 'about:', 'void(']):
                    return
                if source in self.all_extracted_urls:
                    return
                    
                try:
                    async with semaphore:
                        if await self.quick_validate(source, timeout=1.5):
                            valid_sources.add(source)
                            self.all_extracted_urls.add(source)
                except Exception:
                    pass
            
            # 批量并发验证（提高效率）
            batch_size = 50
            for i in range(0, len(all_matches), batch_size):
                batch = list(all_matches)[i:i+batch_size]
                tasks = [validate_and_add(src) for src in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # 递归提取（从 m3u 文件中提取更多链接）
            if depth < 1 and valid_sources:
                for src in list(valid_sources)[:10]:  # 限制递归数量
                    if src.endswith(('.m3u', '.m3u8', '.txt')):
                        try:
                            sub_sources = await self.extract_sources_from_content(src, depth + 1)
                            valid_sources.update(sub_sources)
                        except Exception:
                            pass
            
            return valid_sources
            
        except Exception:
            return set()

    async def crawl_single_source(self, url: str, semaphore: asyncio.Semaphore) -> Tuple[str, Set[str]]:
        """爬取单个源（带超时保护）"""
        async with semaphore:
            try:
                # 验证 + 提取总超时 10 秒
                if not await self.quick_validate(url, timeout=2.0):
                    return (url, set())
                
                extracted = await self.extract_sources_from_content(url)
                if extracted:
                    self.new_sources.update(extracted)
                return (url, extracted)
            except Exception:
                return (url, set())

    async def crawl_all(self) -> Set[str]:
        """爬取所有预设站点（并行优化）"""
        print("🔍 开始异步爬取网络源...")
        print(f"📋 待爬取源数: {len(self.SOURCE_SITES)} 个")

        semaphore = asyncio.Semaphore(10)  # 控制并发数，避免堵塞
        
        # 并行爬取所有源，带进度显示
        tasks = [self.crawl_single_source(url, semaphore) for url in self.SOURCE_SITES]
        
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            if completed % 5 == 0 or completed == len(self.SOURCE_SITES):
                print(f"🔄 进度: {completed}/{len(self.SOURCE_SITES)} 个源已处理")
        
        print(f"✅ 爬取完成: 发现新源 {len(self.new_sources)} 个")

        return self.new_sources


# ==================== 直播源检测 ====================
class StreamChecker:
    """直播源检测器"""
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

    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        """检测单条直播源"""
        if ',' not in line:
            return {"status": "失效", "name": "未知频道", "url": line, "overseas": False}
        
        try:
            name_part, url_part = line.split(',', 1)
            url = url_part.strip()
            name = name_part.strip()[:100]
            
            if not URLCleaner.is_valid(url):
                return {"status": "失效", "name": name, "url": url, "overseas": False}
            
            if not URLCleaner.filter_private_ip(url):
                return {"status": "失效", "name": name, "url": url, "overseas": False}
            
            if any(kw in name for kw in Config.BLACKLIST):
                return {"status": "失效", "name": name, "url": url, "overseas": False}
            
            overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN
            
            if Config.REQUEST_JITTER:
                time.sleep(random.uniform(0.01, 0.05))
            
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)
            return result if result else self._check_with_http(url, name, timeout, proxy, overseas)
            
        except Exception as e:
            return {"status": "失效", "name": "未知频道", "url": line, "reason": str(e)[:30]}

    def _check_with_ffprobe(self, url: str, name: str, timeout: int, 
                           proxy: Optional[str], overseas: bool) -> Optional[Dict[str, Any]]:
        """ffprobe检测"""
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\n'
        
        cmd = [
            'ffprobe', '-headers', headers_str, '-v', 'error',
            '-show_entries', 'stream=codec_type:format=duration,format_name',
            '-probesize', '5000000', '-analyzeduration', '10000000',
            '-timeout', str(int(timeout * 1_000_000)), '-reconnect', '1',
            '-reconnect_streamed', '1', '-reconnect_delay_max', '2',
            '-err_detect', 'ignore_err', '-fflags', 'nobuffer+flush_packets',
            '-user_agent', random.choice(Config.UA_POOL),
        ]
        
        if proxy:
            cmd.extend(['-http_proxy', proxy])
        cmd.append(url)
        
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            stdout, stderr = proc.communicate(timeout=timeout + 2)
            
            stdout_text = stdout.decode('utf-8', errors='ignore').lower()
            stderr_text = stderr.decode('utf-8', errors='ignore').lower()
            
            has_fatal = any(kw in stderr_text for kw in Config.FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_text or 'codec_type=audio' in stdout_text
            
            if not has_fatal and has_stream:
                latency = round(time.time() - start_time, 2)
                return {
                    "status": "有效", "name": name, "url": url, "lat": latency,
                    "overseas": overseas, "quality": self._calc_quality_score(latency, 0)
                }
                
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.communicate()
        except Exception:
            if proc:
                proc.kill()
                proc.communicate()
        
        return None

    def _check_with_http(self, url: str, name: str, timeout: int, 
                         proxy: Optional[str], overseas: bool) -> Dict[str, Any]:
        """HTTP检测"""
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        
        try:
            resp = self.session.head(url, headers=headers, timeout=timeout//2, 
                                    allow_redirects=True, proxies=proxies)
            
            if resp.status_code in (200, 206, 301, 302, 304):
                latency = round(time.time() - start_time, 2)
                return {"status": "有效", "name": name, "url": url, "lat": latency,
                        "overseas": overseas, "quality": self._calc_quality_score(latency, 0)}
            
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, 
                    "reason": f"HTTP{resp.status_code}"}
            
        except Exception:
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, 
                    "reason": "检测超时"}

    @staticmethod
    def _calc_quality_score(latency: float, retries: int) -> int:
        """质量评分计算"""
        if latency <= 1:
            return 100
        elif latency <= 3:
            return max(95 - int(latency * 5), 80)
        elif latency <= 5:
            return max(80 - int(latency * 8), 60)
        else:
            return max(60 - int(latency * 5), 20)


# ==================== 名称处理器 ====================
class NameProcessor:
    _simplify_cache = {}
    _simplify_lock  = threading.Lock()

    OVERSEAS_PREFIX = [
        'TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
        'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠'
    ]

    @staticmethod
    @lru_cache(maxsize=8192)
    def normalize_cctv(name: str) -> str:
        """CCTV 标准化：全角→半角、提取数字、统一格式"""
        if not name:
            return name
        upper = name.upper().replace('ＣＣＴＶ', 'CCTV')
        if 'CCTV' not in upper:
            return name
        m = RegexPatterns.CCTV_STANDARD.search(upper)
        if not m:
            return name
        num  = str(int(m.group(1)))
        plus = m.group(2)
        if num == '5':
            return 'CCTV5+' if (plus or '+' in upper) else 'CCTV5'
        return f'CCTV{num}'

    @staticmethod
    def simplify(text: str) -> str:
        """繁→简，双层缓存"""
        if not text or not isinstance(text, str):
            return text or ''
        with NameProcessor._simplify_lock:
            if text in NameProcessor._simplify_cache:
                return NameProcessor._simplify_cache[text]
        result = zhconv.convert(text, 'zh-hans').strip()
        with NameProcessor._simplify_lock:
            NameProcessor._simplify_cache[text] = result
        return result

    @staticmethod
    @lru_cache(maxsize=8192)
    def clean(name: str) -> str:
        """频道名全流程清洗（借鉴 IPTV-7）"""
        if not name or not name.strip():
            return '未知频道'
        n = RegexPatterns.EMOJI.sub('', name)
        # 境外前缀保留
        for prefix in NameProcessor.OVERSEAS_PREFIX:
            if n.startswith(prefix) and len(n) > len(prefix) + 1:
                pat = rf'({re.escape(prefix)}[A-Za-z0-9\u4e00-\u9fff]+)'
                m = re.search(pat, n)
                if m:
                    n = m.group(1)
                    break
        n = RegexPatterns.NOISE.sub('', n)
        # 优先 CCTV 提取（含全角）
        if not RegexPatterns.HIRES.search(n):
            m = RegexPatterns.CCTV_FIND.search(n)
            if m:
                return NameProcessor.normalize_cctv(m.group(1).upper())
        n = RegexPatterns.SUFFIX.sub('', n)
        n = NameProcessor.simplify(n)
        n = NameProcessor.normalize_cctv(n)
        if not n or RegexPatterns.BLANK.match(n):
            return '未知频道'
        return n.strip()

    @staticmethod
    @lru_cache(maxsize=5000)
    def is_overseas(name: str) -> bool:
        """判断是否为境外频道"""
        return any(kw in name.upper() for kw in Config.OVERSEAS_KEYWORDS)

    @staticmethod
    @lru_cache(maxsize=8192)
    def get_category(name: str) -> Optional[str]:
        """使用预编译正则分类"""
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
        """输出前最终标准化（代理到 clean）"""
        return NameProcessor.clean(name)


# ==================== 主程序 ====================
class IPTVChecker:
    """主程序类"""
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
        """设置日志"""
        self.logger.setLevel(logging.INFO if not Config.DEBUG_MODE else logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def pre_check(self, input_file: Path, output_file: Path) -> bool:
        """环境预检"""
        try:
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
            self.logger.info("✅ ffprobe 正常")
        except Exception:
            self.logger.error("❌ 未安装 ffprobe")
            return False
        
        if not input_file.exists():
            self.logger.warning(f"⚠️ 本地文件不存在: {input_file}")
        
        if Config.AUTO_BACKUP and output_file.exists():
            backup_file = output_file.with_suffix('.txt.bak')
            output_file.rename(backup_file)
            self.logger.info(f"📦 备份原文件: {backup_file}")
        
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]):
        """处理源列表"""
        for line in lines:
            if ',' not in line:
                continue
            
            name_part, url_part = line.split(',', 1)
            url = url_part.strip()
            name = name_part.strip()
            
            if not URLCleaner.is_valid(url):
                continue
            
            if not URLCleaner.filter_private_ip(url):
                continue
            
            fp = URLCleaner.get_fingerprint(url)
            if fp in seen_fp:
                continue
            
            seen_fp.add(fp)
            
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            
            if domain not in domain_lines:
                domain_lines[domain] = []
            domain_lines[domain].append(f"{name},{url}")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        """同步运行模式"""
        # 支持从 run_async 传入已有的去重集合和域名映射（爬虫结果）
        seen_fp = pre_seen_fp if pre_seen_fp is not None else set()
        domain_lines = pre_domain_lines if pre_domain_lines is not None else defaultdict(list)
        lines_to_check = []
        
        # 读取本地文件
        input_path = args.input if args.input else Config.INPUT_FILE
        if Config.ENABLE_LOCAL_CHECK or args.input:
            self.logger.info(f"📂 读取本地文件：{input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    local_lines = [l.strip() for l in f if l.strip()]
                self.process_lines(local_lines, seen_fp, domain_lines)
                self.logger.info(f"✅ 本地处理完成：{len(local_lines)}条")
            except Exception as e:
                self.logger.error(f"❌ 读取本地文件失败: {e}")
        
        # 网络源拉取
        successful_web_sources = []
        if Config.ENABLE_WEB_CHECK and not args.no_web:
            web_sources = Config.PRESET_FILES
            self.logger.info(f"🌐 并发拉取 {len(web_sources)} 个网络源...")
            
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                future_to_url = {
                    executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                    for url in web_sources
                }
                
                success_count = 0
                fail_count = 0
                total_extracted = 0
                
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        lines = future.result()
                        if lines:
                            self.process_lines(lines, seen_fp, domain_lines)
                            success_count += 1
                            total_extracted += len(lines)
                            self.logger.info(f"✅ 拉取成功: {url} ({len(lines)}条)")
                            successful_web_sources.append(url)
                        else:
                            fail_count += 1
                            self.logger.warning(f"❌ 拉取失败: {url} - 返回空内容")
                    except Exception as e:
                        fail_count += 1
                        self.logger.error(f"❌ 拉取异常: {url} - {e}")
                
                self.logger.info(f"📊 网络源拉取完成: 成功{success_count}/{len(web_sources)} | 失败{fail_count} | 提取{total_extracted}条")
                
                if successful_web_sources:
                    Config.save_to_file(successful_web_sources)
        
        # 收集待测源
        if Config.MAX_SOURCES_PER_DOMAIN <= 0:
            for urls in domain_lines.values():
                lines_to_check.extend(urls)
        else:
            for domain, urls in domain_lines.items():
                lines_to_check.extend(urls[:Config.MAX_SOURCES_PER_DOMAIN])
        
        total = len(lines_to_check)
        if total == 0:
            self.logger.warning("⚠️ 没有待测源")
            return
        
        self.stats['total'] = total
        
        overseas_total = sum(1 for ln in lines_to_check if NameProcessor.is_overseas(ln.split(',', 1)[0]))
        cn_total = total - overseas_total
        self.logger.info(f"待测源: {total} 条 | 境内 {cn_total} | 境外 {overseas_total}")
        
        cat_map = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list = []  # 收集失效源列表
        
        real_workers = min(args.workers, total)
        self.logger.info(f"🚀 并发检测：{real_workers}个工作线程")
        
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="测活中", unit="源", ncols=80) as pbar:
            
            futures = [executor.submit(self.checker.check, ln, Config.PROXY) for ln in lines_to_check]
            
            for future in as_completed(futures):
                r = future.result()
                pbar.update(1)
                
                if r["status"] == "有效":
                    self.stats['valid'] += 1
                    key = 'overseas' if r["overseas"] else 'cn'
                    self.stats['by_overseas'][key] += 1
                    
                    cat = NameProcessor.get_category(r["name"])
                    if cat and cat in cat_map:
                        cat_map[cat].append(r)
                        self.stats['by_category'][cat] += 1
                else:
                    self.stats['failed'] += 1
                    if Config.ARCHIVE_FAIL:
                        fail_list.append(f"{r['name']},{r['url']}")
                
                pbar.set_postfix({"有效率": f"{self.stats['valid'] / pbar.n * 100:.1f}%"})
        
        # 写入失效源归档文件
        if Config.ARCHIVE_FAIL and fail_list:
            self.write_failures(fail_list)
        
        # 写入结果
        output_file = args.output if args.output else str(Config.OUTPUT_FILE)
        self.write_results(output_file, cat_map, total)

    async def run_async(self, args):
        """异步运行模式（启用异步爬虫）"""
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)

        # 守卫：仅 ENABLE_WEB_FETCH=True 时才执行爬虫
        if Config.ENABLE_WEB_FETCH:
            self.logger.info("🌐 启动异步爬虫，扫描新源...")
            async with AsyncWebSourceCrawler() as crawler:
                new_sources = await crawler.crawl_all()
                if new_sources:
                    self.logger.info(f"🔍 发现新源: {len(new_sources)} 个")
                    for url in new_sources:
                        if URLCleaner.is_valid(url) and URLCleaner.filter_private_ip(url):
                            fp = URLCleaner.get_fingerprint(url)
                            if fp not in seen_fp:
                                seen_fp.add(fp)
                                domain_lines["crawled_sources"].append(f"爬取源,{url}")
                    self.logger.info(f"✅ 新源已添加到待测列表: {len(domain_lines['crawled_sources'])} 个")

        # 将爬虫结果传入 run()，避免丢失
        self.run(args, pre_seen_fp=seen_fp, pre_domain_lines=domain_lines)

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int):
        """写入结果"""
        output_path = Path(output_file)

        results = []
        for cat in Config.CATEGORY_ORDER:
            channels = cat_map.get(cat, [])
            if not channels:
                continue

            results.append(f"{cat},#genre#")

            # 预排：质量高的优先入 grouped，保证 MAX_LINKS_PER_NAME 收录最优源
            channels.sort(key=lambda x: x.get('quality', 0), reverse=True)

            grouped: Dict[str, List[Dict]] = defaultdict(list)
            for ch in channels:
                # 质量过滤：低于阈值的源不写入结果
                if Config.ENABLE_QUALITY_FILTER and ch.get('quality', 0) < Config.MIN_QUALITY_SCORE:
                    continue
                name = NameProcessor.normalize(ch['name'])
                if len(grouped[name]) < Config.MAX_LINKS_PER_NAME:
                    grouped[name].append(ch)

            if cat == "央衛頻道":
                cctv_ch: Dict[str, List[Dict]] = {}
                other_ch: Dict[str, List[Dict]] = {}
                for name, items in grouped.items():
                    (cctv_ch if name.startswith('CCTV') else other_ch)[name] = items

                # CCTV1 → CCTV17，同名多源质量从高到低
                for num in range(1, 18):
                    key = f"CCTV{num}"
                    if key in cctv_ch:
                        for ch in sorted(cctv_ch[key], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                            results.append(f"{ch['name']},{ch['url']}")

                # CCTV5+，同名多源质量从高到低
                if 'CCTV5+' in cctv_ch:
                    for ch in sorted(cctv_ch['CCTV5+'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                        results.append(f"{ch['name']},{ch['url']}")

                # 其他卫视：频道间按最高质量分从高到低，同名多源质量从高到低
                for name in sorted(other_ch.keys(),
                                   key=lambda n: max(c.get('quality', 0) for c in other_ch[n]),
                                   reverse=True):
                    for ch in sorted(other_ch[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                        results.append(f"{name},{ch['url']}")

            else:
                # 其他所有分组：频道间按最高质量分从高到低，同名多源质量从高到低
                for name in sorted(grouped.keys(),
                                   key=lambda n: max(c.get('quality', 0) for c in grouped[n]),
                                   reverse=True):
                    for ch in sorted(grouped[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                        results.append(f"{name},{ch['url']}")

            results.append("")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(results))
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: {total} 条")
        self.logger.info(f"✅ 有效源: {self.stats['valid']} 条 | 失效: {self.stats['failed']} 条")
        self.logger.info(f"✅ 有效率: {self.stats['valid']/total*100:.1f}%")
        self.logger.info(f"📊 境内: {self.stats['by_overseas']['cn']} | 境外: {self.stats['by_overseas']['overseas']}")
        self.logger.info(f"📋 分类统计:")
        for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: -x[1]):
            if count > 0:
                self.logger.info(f"   {cat}: {count}")
        self.logger.info(f"📁 结果文件: {output_path}")
        self.logger.info(f"{'='*60}\n")

    def write_failures(self, fail_list: List[str]):
        """写入失效源归档文件"""
        fail_path = Config.BASE_DIR / "live_fail.txt"
        try:
            with open(fail_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(fail_list))
            self.logger.info(f"📁 失效源归档: {fail_path} ({len(fail_list)}条)")
        except Exception as e:
            self.logger.warning(f"⚠️ 写入失效源失败: {e}")


# ==================== 命令行入口 ====================
def main():
    """命令行入口"""
    # ✅ 必须最先加载：配置文件中的开关会影响后续所有判断
    Config.init_compiled_rules()
    Config.load_from_file()
    
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 (终极优化版)')
    parser.add_argument('-i', '--input', default=None, help='输入文件路径')
    parser.add_argument('-o', '--output', default=None, help='输出文件路径')
    parser.add_argument('-w', '--workers', type=int, default=80, help='并发线程数')
    parser.add_argument('-t', '--timeout', type=int, default=8, help='超时时间(秒)')
    parser.add_argument('--no-web', action='store_true', help='跳过网络源拉取')
    parser.add_argument('--proxy', default=None, help='代理地址')
    parser.add_argument('--async-crawl', action='store_true', help='启用异步爬虫')
    
    args = parser.parse_args()
    
    if args.timeout:
        Config.TIMEOUT_CN = args.timeout
        Config.TIMEOUT_OVERSEAS = args.timeout * 2
    if args.workers:
        Config.MAX_WORKERS = args.workers
    
    input_file = Path(args.input) if args.input else Config.INPUT_FILE
    output_file = Path(args.output) if args.output else Config.OUTPUT_FILE
    
    checker = IPTVChecker()
    checker.setup_logger()
    
    print(f"{'='*60}")
    print(f"🔍 开始环境预检...")
    if not checker.pre_check(input_file, output_file):
        sys.exit(1)
    print(f"{'='*60}\n")
    
    try:
        # 异步爬虫：仅当 ENABLE_WEB_FETCH=True 或命令行传 --async-crawl 时启用
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            asyncio.run(checker.run_async(args))
        else:
            checker.run(args)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
