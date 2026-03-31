import os, sys, re, time, json, random, argparse, warnings, logging, subprocess, asyncio
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from functools import lru_cache, wraps
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, urlencode
import threading
from queue import Queue
import requests
import httpx
import zhconv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    FAIL_FILE = BASE_DIR / "live_fail.txt"
    LOG_FILE = BASE_DIR / "iptv_check.log"
    STATS_FILE = BASE_DIR / "stats.json"
    CONFIG_FILE = BASE_DIR / "config.json"
    
    ENABLE_WEB_FETCH = False          # 是否启用自动爬取新增网络直播源的功能，开启后会通过异步爬虫挖掘网络上的优质IPTV源
    ENABLE_WEB_CHECK = False          # 是否启用拉取并检测预设网络源的功能，开启后会处理WEB_SOURCES列表中的预设源地址
    ENABLE_LOCAL_CHECK = True         # 是否启用读取并检测本地输入文件的功能，开启后会解析INPUT_FILE指定的本地直播源文件
        
    DEBUG_MODE = False                # 调试模式开关，关闭则不输出调试日志，开启会打印更多运行细节
    AUTO_BACKUP = True                # 自动备份开关，开启后会在覆盖输出文件前，将原有输出文件重命名备份
    ARCHIVE_FAIL = True               # 失效源归档开关，开启后会将检测失败的源写入FAIL_FILE指定的文件
    MAX_WORKERS = 80                  # 直播源检测的最大并发线程数，数值越大检测速度越快，需根据机器性能和网络调整
    FETCH_WORKERS = 8                 # 网络源拉取的最大并发线程数，用于拉取WEB_SOURCES中的远程源文件
    TIMEOUT_CN = 15                   # 境内直播源的检测超时时间，单位：秒，超时判定为源失效
    TIMEOUT_OVERSEAS = 30             # 境外直播源的检测超时时间，单位：秒，境外源网络延迟高，超时时间设更长
    RETRY_COUNT = 3                   # 网络请求重试次数，请求失败时会按设定次数重试
    REQUEST_JITTER = True             # 请求抖动开关，开启后会在请求间添加随机短暂延迟，避免请求频率过高被封禁
    MAX_LINKS_PER_NAME = 3            # 每个频道保留的最大有效链接数，按质量评分从高到低筛选
    FILTER_PRIVATE_IP = True          # 内网IP过滤开关，开启后会剔除源地址中的内网IP（如192.168/10/172段）
    REMOVE_REDUNDANT_PARAMS = False   # URL冗余参数清理开关，关闭则保留原URL所有参数，开启会只保留关键参数
    ENABLE_QUALITY_FILTER = True      # 质量过滤开关，开启后会剔除质量评分低于阈值的直播源
    MIN_QUALITY_SCORE = 60            # 最低质量评分阈值，仅当ENABLE_QUALITY_FILTER为True时生效，低于该值的源会被过滤
    PROXY = None                      # 请求使用代理配置，例如: 'http://127.0.0.1:7897'，境外源检测建议配置代理，None则不使用代理

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
            "METRTV", "MEDICIARTS", "MEDICARTS", "LIFETIME", "LIFETIM", "KPLUS",
            "KOMPASTV", "KMTV", "INEWS", "INDOSIAR", "HUAHEEDAI", "Z 频道", "星球",
            "HKS", "HITS", "HGT", "HB 强档", "HB 家庭", "GTV", "GLOBALTREKKER",
            "FASHIONTV2", "EVE", "EUROSPOR", "EURONEWS", "EBC", "DAZ1", "COLORSTAMIL",
            "有线", "CNBC", "CITRA", "CINEMAX", "CINEMAWORLD", "CHU", "CH8", "CH5",
            "BT", "BLTV", "BERNAMANEWS", "AWESOME", "AWANI", "ARENABOLA", "高点",
            "AOD", "ANIMAX", "ANIMALPLANET", "ALJAZEERA", "AFN", "AEC", "8TV",
            "耀才", "香江", "濠江", "粤语", "闽南语", "繁体", "宝岛", "闽", "麦哲伦",
            "葡语", "香港电台", "RTHK", "TDM", "RHK", "Radio", "好消息", "HOPE", "一电视",
            "纪录", "纪實", "人文", "自然", "地理", "选秀", "相亲", "访谈", "脱口秀"
        ]
    }

    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]
    OVERSEAS_PREFIX = ['TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
                       'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠']

    WEB_SOURCES = [
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
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Mozilla/5.0 (Linux; Android 13; TV Box) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'VLC/3.0.21 LibVLC/3.0.21',
        'Kodi/21.0 (Omega) Android/13.0.0 Sys_CPU/aarch64',
        'TiviMate/4.7.0 (Android TV)',
        'Perfect Player/1.6.0.1 (Linux;Android 13)',
        'Mozilla/5.0 (Linux; Android 12; Amlogic S905X4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
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
                    if hasattr(cls, key):
                        setattr(cls, key, value)
                print(f"✅ 加载配置文件：{cls.CONFIG_FILE}")
            except Exception as e:
                print(f"⚠️ 加载配置文件失败：{e}, 使用默认配置")

    @classmethod
    def init_compiled_rules(cls):
        """✅ 初始化时编译正则表达式"""
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
    EMOJI = re.compile(
        r'[\U00010000-\U0010ffff\U00002600-\U000027ff\U0000f600-\U0000f6ff'
        r'\U0000f300-\U0000f3ff\U00002300-\U000023ff\U00002500-\U000025ff'
        r'\U00002100-\U000021ff\U000000a9\U000000ae\U00002000-\U0000206f'
        r'\U00002460-\U000024ff\U00001f00-\U00001fff]+',
        re.UNICODE
    )
    CCTV_FIND = re.compile(r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)')
    CCTV_STANDARD = re.compile(r'CCTV\D*?(\d{1,2})\s*\+?', re.IGNORECASE)
    HIRES = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清')
    NOISE = re.compile(r'\(.*?\)|\)|\[.*?\]|【.*?】|《.*?》|<.*?>|\{.*?\}')
    SUFFIX = re.compile(r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|4Gtv|540p|高清 | 超清 | 超高清 | 标清 | 直播 | 主线 | 台$')
    BLANK = re.compile(r'^[\s\-—_～•·:·]+$')
    TVG_NAME = re.compile(r'tvg-name="([^"]+)"')
    DATE_TAG = re.compile(r'更新日期:.*')


# ==================== 装饰器 ====================
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


# ==================== 核心工具类 ====================
class IPChecker:
    @staticmethod
    def is_private(host: str) -> bool:
        return bool(RegexPatterns.PRIVATE_IP.match(host)) if host else True


class URLCleaner:
    """✅ 优化：使用线程安全的缓存"""
    _cache_lock = threading.Lock()
    _fingerprint_cache = {}
    
    @staticmethod
    def clean_params(url: str) -> str:
        if not Config.REMOVE_REDUNDANT_PARAMS:
            return url
        try:
            parsed = urlparse(url)
            keep_params = {'codec', 'resolution', 'bitrate', 'stream', 'channel', 'id', 'pid', 'u', 'token', 'key'}
            query_dict = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in query_dict.items() if any(kw in k.lower() for kw in keep_params)}
            return parsed._replace(query=urlencode(filtered, doseq=True)).geturl()
        except Exception:
            return url

    @staticmethod
    def get_fingerprint(url: str) -> str:
        """✅ 优化：快速路径避免重复计算"""
        with URLCleaner._cache_lock:
            if url in URLCleaner._fingerprint_cache:
                return URLCleaner._fingerprint_cache[url]
        
        try:
            cleaned = URLCleaner.clean_params(url)
            parsed = urlparse(cleaned)
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            fp = f"{host}{port}{parsed.path}{parsed.query or ''}".lower()
        except Exception:
            fp = url.lower()
        
        with URLCleaner._cache_lock:
            URLCleaner._fingerprint_cache[url] = fp
        return fp

    @staticmethod
    def is_valid(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            return False


class NameProcessor:
    """✅ 优化：缓存所有中文转简体的操作"""
    _simplify_cache = {}
    _simplify_lock = threading.Lock()
    
    @staticmethod
    @lru_cache(maxsize=16384)
    def normalize_cctv(name: str) -> str:
        if not name:
            return name
        upper_name = name.upper().replace("ＣＣＴＶ", "CCTV")
        if not upper_name.startswith('CCTV'):
            return name
        match = RegexPatterns.CCTV_STANDARD.search(upper_name)
        if not match:
            return name
        num = str(int(match.group(1)))
        return f"CCTV5+" if (num == "5" and "+" in upper_name) else f"CCTV{num}"

    @staticmethod
    def simplify(text: str) -> str:
        """✅ 优化：使用双层缓存减少转换次数"""
        if not text or not isinstance(text, str):
            return text or ""
        
        with NameProcessor._simplify_lock:
            if text in NameProcessor._simplify_cache:
                return NameProcessor._simplify_cache[text]
        
        result = zhconv.convert(text, 'zh-hans').strip()
        
        with NameProcessor._simplify_lock:
            NameProcessor._simplify_cache[text] = result
        return result

    @staticmethod
    @lru_cache(maxsize=16384)
    def clean(name: str) -> str:
        if not name or name.strip() == "":
            return "未知频道"
        
        n = RegexPatterns.EMOJI.sub('', name)
        
        for prefix in Config.OVERSEAS_PREFIX:
            if n.startswith(prefix) and len(n) > len(prefix) + 1:
                pattern = rf'({re.escape(prefix)}[A-Za-z0-9\u4e00-\u9fff]+)'
                m = re.search(pattern, n)
                if m:
                    n = m.group(1)
                    break
        
        n = RegexPatterns.NOISE.sub('', n)
        n = NameProcessor.normalize_cctv(n)
        
        if not RegexPatterns.HIRES.search(n):
            m = RegexPatterns.CCTV_FIND.search(n)
            if m:
                return NameProcessor.normalize_cctv(m.group(1).upper())
        
        n = RegexPatterns.SUFFIX.sub('', n)
        n = NameProcessor.simplify(n)
        n = NameProcessor.normalize_cctv(n)
        
        return "未知频道" if (not n or RegexPatterns.BLANK.match(n)) else n.strip()

    @staticmethod
    @lru_cache(maxsize=8192)
    def get_category(name: str) -> Optional[str]:
        """✅ 优化：使用预编译正则表达式"""
        s = NameProcessor.simplify(name)
        if any(kw in s for kw in Config.BLACKLIST):
            return None
        
        for cat in Config.CATEGORY_ORDER[:-1]:
            if cat in Config.CATEGORY_RULES_COMPILED:
                if Config.CATEGORY_RULES_COMPILED[cat].search(s):
                    return cat
        
        return "其他頻道"

    @staticmethod
    @lru_cache(maxsize=8192)
    def is_overseas(name: str) -> bool:
        s = NameProcessor.simplify(name).upper()
        return any(kw.upper() in s for kw in Config.OVERSEAS_KEYWORDS)


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
                continue
            
            if extinf_line and ('http://' in line or 'https://' in line):
                m = RegexPatterns.TVG_NAME.search(extinf_line)
                if m:
                    name_part = m.group(1).strip()
                elif ',' in extinf_line:
                    name_part = extinf_line.rsplit(',', 1)[-1].strip()
                else:
                    name_part = '未知频道'
                
                name_part = RegexPatterns.DATE_TAG.sub('', name_part).strip() or '未知频道'
                parsed.append(f"{name_part},{line}")
                extinf_line = None
        
        return parsed


# ==================== 网络源获取 ====================
class WebSourceFetcher:
    """✅ 优化：连接池复用，减少 SSL 握手开销"""
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.FETCH_WORKERS,
            pool_maxsize=Config.FETCH_WORKERS,
            max_retries=1
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    def __del__(self):
        self.session.close()

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
        timeout = (10, 60) if "githubusercontent" in url else (10, 45)
        
        resp = self.session.get(url, headers=headers, timeout=timeout, 
                               allow_redirects=True, proxies=proxies, stream=False)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'
        
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
        
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


# ==================== 异步爬虫 (来自 IPTV_Optimized.py) ====================
class AsyncWebSourceCrawler:
    SOURCE_SITES = [
        "https://raw.githubusercontent.com/fanmingming/live/main/",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/",
        "https://iptv-org.github.io/iptv/countries/",
    ]
    PRESET_FILES = [
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
    ]

    def __init__(self):
        self.sem = asyncio.Semaphore(30)

    async def _quick_check(self, url: str) -> bool:
        async with self.sem:
            async with httpx.AsyncClient(timeout=3, follow_redirects=True, verify=False) as client:
                try:
                    r = await client.head(url)
                    return r.status_code < 400
                except Exception:
                    return False

    async def _fetch_content(self, url: str) -> str:
        async with self.sem:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=False) as client:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    return r.text[:80000]
                except Exception:
                    return ""

    async def crawl(self) -> Set[str]:
        sources = set(self.PRESET_FILES)
        print("  📦 加载预设优质源... 已加载 5 个")
        
        print("  🔍 异步扫描源站点目录...")
        tasks = [self._quick_check(base.rstrip('/') + '/' + name)
                 for base in self.SOURCE_SITES
                 for name in ['tv.m3u', 'live.txt', 'iptv.m3u', 'result.txt', 'cn.m3u']]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        print("  ⛏️  异步挖掘更多源...")
        await self._mine_sources_from_content(sources)
        
        print(f"  📊 发现源总数：{len(sources)}")
        return sources

    async def _mine_sources_from_content(self, sources: Set[str]):
        checked = set()
        tasks = [self._fetch_content(url) for url in list(sources)[:5]]
        contents = await asyncio.gather(*tasks, return_exceptions=True)
        for content in contents:
            if not isinstance(content, str) or not content:
                continue
            try:
                for link in re.findall(r'https?://[^\s\'"<>]+(?:m3u|m3u8|txt)', content):
                    if link not in checked and URLCleaner.is_valid(link):
                        if await self._quick_check(link):
                            sources.add(link)
                            checked.add(link)
            except Exception:
                continue

    async def validate_sources(self, sources: List[str]) -> Set[str]:
        print("  ✅ 异步验证源的有效性...")
        valid = set()
        async with httpx.AsyncClient(timeout=25, limits=httpx.Limits(max_connections=50), verify=False) as client:
            tasks = [self._validate_one(client, url) for url in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for url, ok in zip(sources, results):
                if isinstance(ok, bool) and ok:
                    valid.add(url)
        print(f"  📊 验证完成：有效 {len(valid)}/{len(sources)}")
        return valid

    async def _validate_one(self, client: httpx.AsyncClient, url: str) -> bool:
        try:
            r = await client.get(url)
            return r.status_code < 400 and len(r.text) > 100
        except Exception:
            return False


# ==================== 流媒体检测 ====================
class StreamChecker:
    """✅ 优化：连接池 + 流式读取"""
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.MAX_WORKERS,
            pool_maxsize=Config.MAX_WORKERS,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def __del__(self):
        self.session.close()

    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        try:
            parts = line.split(',', 1)
            if len(parts) != 2:
                return {"status": "失效", "name": "未知频道", "url": line, "reason": "格式无效"}
            
            name, url = parts[0].strip(), parts[1].strip()
            
            if not URLCleaner.is_valid(url):
                return {"status": "失效", "name": name or "未知频道", "url": url, "reason": "URL 无效"}
            
            host = urlparse(url).hostname or ""
            if Config.FILTER_PRIVATE_IP and IPChecker.is_private(host):
                return {"status": "失效", "name": name, "url": url, "reason": "内网地址"}
            
            overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN
            
            if Config.REQUEST_JITTER:
                time.sleep(random.uniform(0.02, 0.1))
            
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)
            return result if result else self._check_with_http(url, name, timeout, proxy, overseas)
            
        except Exception as e:
            return {"status": "失效", "name": "未知频道", "url": line, "reason": str(e)[:30]}

    def _check_with_ffprobe(self, url: str, name: str, timeout: int, 
                           proxy: Optional[str], overseas: bool) -> Optional[Dict[str, Any]]:
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\n'
        
        cmd = [
            'ffprobe', '-headers', headers_str, '-v', 'error',
            '-show_entries', 'stream=codec_type:format=duration,format_name',
            '-probesize', '10000000', '-analyzeduration', '20000000',
            '-timeout', str(int(timeout * 1_000_000)), '-reconnect', '3',
            '-reconnect_streamed', '1', '-reconnect_delay_max', '3',
            '-err_detect', 'ignore_err', '-fflags', 'nobuffer+flush_packets',
            '-user_agent', random.choice(Config.UA_POOL),
        ]
        
        if proxy:
            cmd.extend(['-http_proxy', proxy])
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


# ==================== 主应用类 ====================
class IPTVChecker:
    def __init__(self):
        Config.init_compiled_rules()
        self.logger = self._setup_logger()
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats = {'start_time': time.time(), 'total': 0, 'valid': 0, 'failed': 0,
                      'by_category': defaultdict(int), 'by_overseas': {'cn': 0, 'overseas': 0}}
        Config.load_from_file()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("IPTV_CHECK")
        logger.setLevel(logging.INFO)
        
        if logger.handlers:
            logger.handlers.clear()
        
        fh = logging.FileHandler(Config.LOG_FILE, encoding='utf-8', mode='w')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        fh.setLevel(logging.INFO)
        
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(message)s'))
        ch.setLevel(logging.INFO)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        return logger

    def pre_check(self, input_file: Path, output_file: Path) -> bool:
        self.logger.info("=" * 70)
        self.logger.info("🔍 开始环境预检...")
        
        try:
            proc = subprocess.run(['ffprobe', '-version'], capture_output=True, timeout=5, shell=False)
            if proc.returncode != 0:
                self.logger.error("❌ 未找到 ffprobe")
                return False
            self.logger.info("✅ ffprobe 正常")
        except Exception as e:
            self.logger.error(f"❌ 环境检查失败：{e}")
            return False
        
        if input_file.exists():
            self.logger.info(f"✅ 本地文件：{input_file}")
        else:
            self.logger.warning(f"⚠️ 本地文件不存在")
        
        if Config.AUTO_BACKUP and output_file.exists():
            backup = output_file.parent / f"{output_file.stem}_backup_{int(time.time())}.txt"
            try:
                output_file.rename(backup)
                self.logger.info(f"✅ 已备份")
            except Exception:
                pass
        
        self.logger.info("=" * 70)
        return True

    def read_local_file(self, input_file: Path) -> List[str]:
        if not input_file.exists():
            return []
        
        try:
            with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.strip() for l in f if l.strip()]
            
            if any(l.startswith('#EXTM3U') for l in lines[:10]):
                return M3UParser.parse(lines)
            
            parsed = []
            for line in lines:
                if ',' not in line or '://' not in line:
                    continue
                parts = line.split(',', 1)
                name, url = parts[0].strip(), parts[1].strip()
                if name and URLCleaner.is_valid(url):
                    parsed.append(f"{name},{url}")
            return parsed
        except Exception as e:
            self.logger.error(f"读取文件失败：{e}")
            return []

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]) -> None:
        for line in lines:
            if ',' not in line:
                continue
            
            name_part, url = line.split(',', 1)
            url = url.strip()
            fp = URLCleaner.get_fingerprint(url)
            
            if fp not in seen_fp:
                seen_fp.add(fp)
                clean_name = NameProcessor.clean(name_part.strip())
                if clean_name:
                    host = urlparse(url).hostname or "unknown"
                    domain_lines[host].append(f"{clean_name},{url}")

    def _write_file_atomic(self, file_path: Path, content: str) -> None:
        tmp = file_path.with_suffix('.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(content)
            tmp.replace(file_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    def write_results(self, output_file: Path, cat_map: Dict[str, List[Dict[str, Any]]]) -> None:
        duration = time.time() - self.stats['start_time']
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"// 更新：{time.strftime('%Y-%m-%d %H:%M:%S')} | "
                   f"有效 {self.stats['valid']}/{self.stats['total']} | "
                   f"耗时 {duration:.1f}s\n\n")
            
            for cat in Config.CATEGORY_ORDER:
                items = cat_map.get(cat, [])
                if not items:
                    continue
                
                f.write(f"{cat},#genre#\n")
                
                grouped = defaultdict(list)
                for item in items:
                    if Config.ENABLE_QUALITY_FILTER and item.get('quality', 0) < Config.MIN_QUALITY_SCORE:
                        continue
                    grouped[item['name']].append(item)
                
                if cat == "央衛頻道":
                    self._write_cctv_category(f, grouped)
                else:
                    self._write_normal_category(f, grouped)
                
                f.write("\n")

    def _write_cctv_category(self, f, grouped: Dict) -> None:
        cctv_channels, other = {}, {}
        for name, items in grouped.items():
            (cctv_channels if name.startswith('CCTV') else other)[name] = items
        
        for num in range(1, 18):
            if f"CCTV{num}" in cctv_channels:
                for item in sorted(cctv_channels[f"CCTV{num}"], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                    f.write(f"{item['name']},{item['url']}\n")
        
        if 'CCTV5+' in cctv_channels:
            for item in sorted(cctv_channels['CCTV5+'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")
        
        for name in sorted(other.keys()):
            for item in sorted(other[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")

    def _write_normal_category(self, f, grouped: Dict) -> None:
        for name in sorted(grouped.keys()):
            for item in sorted(grouped[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")

    def write_failures(self, fail_list: List[str]) -> None:
        if not (Config.ARCHIVE_FAIL and fail_list):
            return
        content = f"// 失效源 | {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(fail_list)}条\n\n"
        content += "\n".join(fail_list) + "\n"
        self._write_file_atomic(Config.FAIL_FILE, content)

    def write_stats(self) -> None:
        stats = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'duration': time.time() - self.stats['start_time'],
            'total': self.stats['total'],
            'valid': self.stats['valid'],
            'failed': self.stats['failed'],
            'valid_rate': f"{self.stats['valid']/max(self.stats['total'], 1)*100:.1f}%",
            'by_category': dict(self.stats['by_category']),
            'by_overseas': self.stats['by_overseas'],
        }
        
        try:
            with open(Config.STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def run(self, args: argparse.Namespace) -> None:
        if args.proxy:
            Config.PROXY = args.proxy
        if args.timeout:
            Config.TIMEOUT_CN = args.timeout
        if args.workers:
            Config.MAX_WORKERS = args.workers
        
        input_file = Path(args.input) if args.input else Config.INPUT_FILE
        output_file = Path(args.output) if args.output else Config.OUTPUT_FILE
        
        if not self.pre_check(input_file, output_file):
            sys.exit(1)
        
        seen_fp = set()
        domain_lines = defaultdict(list)
        
        # ✅ 本地文件检查
        if Config.ENABLE_LOCAL_CHECK:
            self.logger.info("📂 读取本地文件...")
            local_lines = self.read_local_file(input_file)
            self.process_lines(local_lines, seen_fp, domain_lines)
            self.logger.info(f"✅ 本地处理完成：{len(seen_fp)}条")
        else:
            self.logger.info("⏭️  跳过本地文件检查")
        
        web_sources = set(Config.WEB_SOURCES)
        
        # ✅ 网页源爬取 (新增功能 - 来自 IPTV_Optimized.py)
        if Config.ENABLE_WEB_FETCH and not args.no_web:
            self.logger.info("🕷️ 异步爬取网页源（asyncio + httpx）...")
            crawler = AsyncWebSourceCrawler()
            start = time.time()
            try:
                new_sources = asyncio.run(crawler.crawl())
                web_sources = web_sources | new_sources
                self.logger.info(f"🕷️ 爬取完成：新增{len(new_sources)}个 | 总计{len(web_sources)}个 | 耗时{time.time()-start:.1f}s")
                
                self.logger.info("🔍 异步验证源的有效性...")
                valid_sources = asyncio.run(crawler.validate_sources(list(web_sources)))
                if valid_sources:
                    Config.WEB_SOURCES = list(valid_sources)
            except Exception as e:
                self.logger.error(f"爬取失败：{e}")
        
        # ✅ 网络源拉取
        if Config.ENABLE_WEB_CHECK and web_sources and not args.no_web:
            self.logger.info(f"🌐 拉取 {len(web_sources)} 个网络源...")
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                for future in as_completed([executor.submit(self.fetcher.fetch, url, Config.PROXY) 
                                            for url in web_sources]):
                    try:
                        lines = future.result()
                        self.process_lines(lines, seen_fp, domain_lines)
                    except Exception:
                        pass
            self.logger.info(f"✅ 网络源完成：{len(seen_fp)}条")
        else:
            if not Config.ENABLE_WEB_CHECK:
                self.logger.info("⏭️  跳过网络源拉取")
        
        lines_to_check = []
        for host_lines in domain_lines.values():
            lines_to_check.extend(host_lines)
        random.shuffle(lines_to_check)
        
        total = len(lines_to_check)
        if total == 0:
            self.logger.error("没有待测源")
            return
        
        self.stats['total'] = total
        cn_total = sum(1 for ln in lines_to_check if not NameProcessor.is_overseas(ln.split(',')[0]))
        self.logger.info(f"待测：{total}条 | 境内 {cn_total} | 境外 {total-cn_total}")
        
        cat_map = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list = []
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
                    key = 'overseas' if r.get("overseas") else 'cn'
                    self.stats['by_overseas'][key] += 1
                    
                    cat = NameProcessor.get_category(r["name"])
                    if cat and cat in cat_map:
                        cat_map[cat].append(r)
                        self.stats['by_category'][cat] += 1
                else:
                    self.stats['failed'] += 1
                    if Config.ARCHIVE_FAIL:
                        fail_list.append(f"{r['name']},{r['url']} | {r.get('reason', '')}")
                
                pbar.set_postfix({"有效率": f"{self.stats['valid']/pbar.n*100:.1f}%"})
        
        self.logger.info("💾 写入结果...")
        self.write_results(output_file, cat_map)
        self.write_failures(fail_list)
        self.write_stats()
        
        duration = time.time() - self.stats['start_time']
        self.logger.info("=" * 70)
        self.logger.info(f"✅ 完成! {self.stats['valid']}/{total} = {self.stats['valid']/total*100:.1f}%")
        self.logger.info(f"⏱️  耗时：{duration:.1f}秒")
        self.logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具')
    parser.add_argument('--input', type=str, help='输入文件')
    parser.add_argument('--output', type=str, help='输出文件')
    parser.add_argument('--workers', type=int, default=Config.MAX_WORKERS)
    parser.add_argument('--proxy', type=str)
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--no-web', action='store_true')
    parser.add_argument('--no-quality-filter', action='store_true')
    parser.add_argument('--min-quality', type=int, default=60)
    args = parser.parse_args()

    if args.no_quality_filter:
        Config.ENABLE_QUALITY_FILTER = False
    else:
        Config.MIN_QUALITY_SCORE = args.min_quality

    checker = IPTVChecker()
    checker.run(args)


if __name__ == "__main__":
    main()