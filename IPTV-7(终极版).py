#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IPTV直播源检测与整理工具 - 终极版"""

import os, sys, re, time, json, random, argparse, warnings, logging, subprocess
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from functools import lru_cache, wraps
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, urlencode

import requests
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
    
    DEBUG_MODE = False
    AUTO_BACKUP = True
    ARCHIVE_FAIL = True
    MAX_WORKERS = 80
    FETCH_WORKERS = 8
    TIMEOUT_CN = 15
    TIMEOUT_OVERSEAS = 30
    RETRY_COUNT = 3
    REQUEST_JITTER = True
    MAX_LINKS_PER_NAME = 3
    FILTER_PRIVATE_IP = True
    REMOVE_REDUNDANT_PARAMS = False
    ENABLE_QUALITY_FILTER = True
    MIN_QUALITY_SCORE = 60
    PROXY = None  # 代理配置，例如: 'http://127.0.0.1:7897'
    
    WEB_SOURCES = [
        "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
        "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt",
        "http://txt.gt.tc/users/HKTV.txt",
        "https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt",
        "https://tvv.tw/https://raw.githubusercontent.com/tushen6/xxooo/refs/heads/main/TV/lzxw.txt",
        "https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u",
        "https://raw.githubusercontent.com/FGBLH/FG/refs/heads/main/%E6%B8%AF%E5%8F%B0%E5%A4%A7%E9%99%86",
        "https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt",
        "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
        "http://tv123.vvvv.ee/tv.m3u",
        "https://php.946985.filegear-sg.me/test.m3u",
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
    
    BLACKLIST = ["购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", "教程", "联系", "推广", "免费"]
    OVERSEAS_KEYWORDS = [
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "beIN",
    ]
    FATAL_ERROR_KEYWORDS = [
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
    ]
    
    CATEGORY_RULES = {
        "4K專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球", "台球", "棋", "赛马",
            "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技", "SPORT", "SPOTV", "BALL", "晴彩", "咪咕",
            "NBA", "英超", "西甲", "意甲", "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J联赛",
            "K联赛", "美职", "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
            "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运", "亚运", "世界杯",
            "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA", "五大联赛", "Pac-12", "大学体育", "文体",
        ],
        "音樂頻道": [
            "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV", "流行", "嘻哈", "摇滚",
            "古典", "爵士", "民谣", "电音", "EDM", "纯音乐", "伴奏", "Karaoke", "首",
            "Channel V", "Trace", "VH1", "MTV Hits", "MTV Live", "KKBOX", "韩国女团", "女团",
            "Space Shower", "KAYOPOPS", "Musicon",
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼儿", "宝宝", "宝贝", "炫动",
            "卡通片", "动漫片", "动画片", "小公", "CARTOON", "ANIME", "ANIMATION", "KIDS",
            "睛彩青少", "青少", "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS",
            "TOON", "BOOMERANG", "尼克",
        ],
        "影視劇集": [
            "至臻", "爱奇艺", "爆谷", "HBO", "POPC", "邵氏", "娱乐", "经典", "戏", "黄金", "亚洲",
            "MOVIE", "SERIES", "天映", "黑莧", "龙华", "片", "偶像", "影剧", "映画", "影迷", "华语",
            "新视觉", "好莱坞", "采昌", "美亚", "纬来", "ASTRO", "剧集", "电影", "影院", "影视",
            "剧场", "STAR", "SHORTS", "NETFLIX", "Prime", "Disney+", "Paramount+", "电视剧",
            "Peacock", "Max", "Showtime", "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime",
            "Hallmark", "华纳", "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
            "Marvel", "DCU", "Star Wars", "剧场版", "纪录片", "真人秀", "综艺", "真人实境",
            "DLIFE", "NECO", "The Cinema", "家庭剧场", "Homedrama", "Family Gekijo", "Entermei Tele",
        ],
        "港澳台頻": [
            "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理", "香港", "华文", "八度",
            "华艺", "环球", "生命", "镜", "澳", "台湾", "年代", "明珠", "唯心", "公视", "东森", "三立",
            "爱尔达", "NOW", "VIU", "HBO", "STAR", "星空", "纬来", "非凡", "中天", "无线", "寰宇", "GOOD",
            "ROCK", "华视", "台视", "中视", "民视", "TVBS", "八大", "龙祥", "靖天", "AXN", "KIX", "HOY",
            "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视", "大爱", "人间", "客家", "壹电视", "镜电视",
            "中视新闻", "民视新闻", "三立新闻", "东森新闻", "TVB News", "TVBS News", "SET News", "FTV News",
            "CTI", "CTS", "PTS", "NTV", "Fuji TV", "NHK", "TBS", "WOWOW", "Sky", "ESPN", "beIN", "DAZN",
            "Eleven Sports", "SPOTV NOW", "TrueVisions", "Astro", "Unifi TV", "HyppTV", "myTV SUPER", "Now TV",
            "Cable TV", "PCCW", "HKTV", "Viu", "Netflix", "Disney+", "TVBS", "TVBSG", "TVBSASIA", "TVBPLUS",
            "TTV", "TTV新闻", "TTVFINANCE", "TRANSTV", "TLC", "SURIA", "SUPERFREE", "SUNTV", "SUNEWS",
            "SUMUSIC", "SULIF", "SUKART", "SPOT2", "SPOT", "SONYTEN3", "SET新闻", "RTV", "ROCKACTION",
            "RIA", "QJ", "OKEY", "NOW财经", "NOW新闻", "NHKWORLD", "NET", "MTLIVE", "METRTV",
            "MEDICIARTS", "MEDICARTS", "LIFETIME", "LIFETIM", "KPLUS", "KOMPASTV", "KMTV", "KBSWORLD",
            "INEWS", "INDOSIAR", "HUAHEEDAI", "HOY资讯", "HOYINFOTAINMENT", "HOY78", "HOY77", "HOY76",
            "HKS", "HITS", "HGT", "HB强档", "HB家庭", "GTVVARIETY", "GTVDRAMA", "GOOD福音2", "GOODTV福音",
            "GLOBALTREKKER", "FTV新闻", "FTVONE", "FTV", "FASHIONTV2", "EVE", "EUROSPOR", "EURONEWS",
            "EBCSUPERTV", "EBCFINANCIAL新闻", "DAZ1", "CTI新闻+", "CTITVVARIETY", "COLORSTAMIL", "有线",
            "CNN印尼", "CNBC", "CITRA", "CINEMAX", "CINEMAWORLD", "CHU", "CH8", "CH5", "BT", "BLTV",
            "BERNAMANEWS", "BBCWORLD", "BBCBEEBIES", "B4UMUSIC", "AXN", "AWESOME", "AWESOM", "AWANI",
            "ARENABOLA", "AOD", "ANIMAX", "ANIMALPLANET", "ANIMALPLANE", "ALJAZEERA", "AFN", "AF", "AEC",
            "8TV", "联合国", "UNTV", "联合国 UNTV", "耀才财经", "TVBJ1", "TVBD", "TVBASIANDRAMA", "TVB1", "TV9",
        ],
    }
    
    CATEGORY_ORDER = ["4K專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]
    OVERSEAS_PREFIX = ['TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
                       'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠']
    
    @classmethod
    def load_from_file(cls):
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for key, value in config.items():
                    if hasattr(cls, key):
                        setattr(cls, key, value)
                print(f"✅ 加载配置文件: {cls.CONFIG_FILE}")
            except Exception as e:
                print(f"⚠️ 加载配置文件失败: {e}, 使用默认配置")


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
    SUFFIX = re.compile(r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|4Gtv|540p|高清|超清|超高清|标清|直播|主线|台$')
    BLANK = re.compile(r'^[\s\-—_～•·:·]+$')
    TVG_NAME = re.compile(r'tvg-name="([^"]+)"')
    DATE_TAG = re.compile(r'更新日期:.*')


# ==================== 装饰器 ====================

def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt, current_delay = 0, delay
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    print(f"⚠️ {func.__name__} 第{attempt}次失败: {e}, {current_delay:.1f}s后重试...")
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


# ==================== 核心工具类 ====================

class IPChecker:
    @staticmethod
    def is_private(host: str) -> bool:
        if not host:
            return True
        return bool(RegexPatterns.PRIVATE_IP.match(host))


class URLCleaner:
    @staticmethod
    def clean_params(url: str) -> str:
        if not Config.REMOVE_REDUNDANT_PARAMS:
            return url
        try:
            parsed = urlparse(url)
            keep_params = ['codec', 'resolution', 'bitrate', 'stream', 'channel', 'id', 'pid', 'u', 'token', 'key']
            query_dict = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in query_dict.items() if any(kw in k.lower() for kw in keep_params)}
            return parsed._replace(query=urlencode(filtered, doseq=True)).geturl()
        except Exception:
            return url
    
    @staticmethod
    def get_fingerprint(url: str) -> str:
        try:
            cleaned = URLCleaner.clean_params(url)
            parsed = urlparse(cleaned)
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            return f"{host}{port}{parsed.path}{parsed.query or ''}".lower()
        except Exception:
            return url.lower()
    
    @staticmethod
    def is_valid(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            return False


class NameProcessor:
    @staticmethod
    @lru_cache(maxsize=8192)
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
        if num == "5":
            return "CCTV5+" if "+" in upper_name else "CCTV5"
        return f"CCTV{num}"
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def simplify(text: str) -> str:
        if not text or not isinstance(text, str):
            return text or ""
        return zhconv.convert(text, 'zh-hans').strip()
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def clean(name: str) -> str:
        if not name or name.strip() == "":
            return "未知频道"
        
        n = RegexPatterns.EMOJI.sub('', name)
        
        # 提取境外前缀
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
        
        if not n or RegexPatterns.BLANK.match(n):
            return "未知频道"
        
        return n.strip()
    
    @staticmethod
    @lru_cache(maxsize=4096)
    def get_category(name: str) -> Optional[str]:
        s = NameProcessor.simplify(name)
        if any(k in s for k in Config.BLACKLIST):
            return None
        
        for cat in Config.CATEGORY_ORDER[:-1]:
            keywords = Config.CATEGORY_RULES.get(cat, [])
            if cat == "各地衛視":
                if "卫视" in s:
                    return cat
            elif any(k in s for k in keywords):
                return cat
        
        return "其他頻道"
    
    @staticmethod
    @lru_cache(maxsize=4096)
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


class WebSourceFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    def __del__(self):
        self.session.close()
    
    @retry(max_attempts=3, delay=1, backoff=2)
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
        timeout = (15, 90) if "githubusercontent" in url else (15, 60)
        
        resp = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=True, proxies=proxies)
        resp.raise_for_status()
        
        resp.encoding = resp.apparent_encoding or 'utf-8'
        text_content = resp.text
        
        lines = [l.strip() for l in text_content.splitlines() if l.strip()]
        
        if any(l.startswith('#EXTM3U') for l in lines[:10]):
            parsed = M3UParser.parse(lines)
        else:
            parsed = []
            for line in lines:
                if ',' not in line:
                    continue
                parts = line.split(',', 1)
                name_part, url_part = parts[0].strip(), parts[1].strip()
                if not URLCleaner.is_valid(url_part):
                    continue
                parsed.append(f"{name_part},{url_part}")
        
        # 去重
        unique, seen = [], set()
        for item in parsed:
            if ',' not in item:
                continue
            _, url = item.split(',', 1)
            fp = URLCleaner.get_fingerprint(url.strip())
            if fp not in seen:
                seen.add(fp)
                unique.append(item)
        
        return unique


class StreamChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
    
    def __del__(self):
        self.session.close()
    
    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        try:
            name, url = [x.strip() for x in line.split(',', 1)]
            if not URLCleaner.is_valid(url):
                return {"status": "失效", "name": name or "未知频道", "url": url, "reason": "URL格式无效"}
            
            overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN
            
            if Config.REQUEST_JITTER:
                time.sleep(random.uniform(0.05, 0.2))
            
            host = urlparse(url).hostname or ""
            if Config.FILTER_PRIVATE_IP and IPChecker.is_private(host):
                return {"status": "失效", "name": name, "url": url, "reason": "内网/本地地址"}
            
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)
            if result:
                return result
            
            return self._check_with_http(url, name, timeout, proxy, overseas)
            
        except Exception as e:
            return {"status": "失效", "name": "未知频道", "url": line, "reason": f"解析失败: {e}"}
    
    def _check_with_ffprobe(self, url: str, name: str, timeout: int, 
                           proxy: Optional[str], overseas: bool) -> Optional[Dict[str, Any]]:
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\nOrigin: {domain}\r\n'
        
        for retry in range(Config.RETRY_COUNT + 1):
            probe_size = '5000000' if retry == 0 else '15000000'
            analyze_dur = '10000000' if retry == 0 else '30000000'
            
            cmd = [
                'ffprobe',
                '-headers', headers_str,
                '-v', 'error',
                '-show_entries', 'stream=codec_type:format=duration,format_name',
                '-probesize', probe_size,
                '-analyzeduration', analyze_dur,
                '-timeout', str(int(timeout * 1_000_000)),
                '-reconnect', '3',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                '-err_detect', 'ignore_err',
                '-fflags', 'nobuffer+flush_packets+genpts',
                '-flags', 'low_delay',
                '-strict', '-2',
                '-allowed_extensions', 'ALL',
                '-user_agent', random.choice(Config.UA_POOL),
            ]
            
            if proxy:
                cmd.extend(['-http_proxy', proxy])
            
            cmd.append(url)
            
            proc = None
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
                stdout, stderr = proc.communicate(timeout=timeout + 5)
                
                stdout_content = stdout.decode('utf-8', errors='ignore').lower()
                stderr_content = stderr.decode('utf-8', errors='ignore').lower()
                
                has_fatal = any(kw in stderr_content for kw in Config.FATAL_ERROR_KEYWORDS)
                has_stream = 'codec_type=video' in stdout_content or 'codec_type=audio' in stdout_content
                has_format = 'format_name=' in stdout_content
                
                if not has_fatal and (has_stream or has_format):
                    latency = round(time.time() - start_time, 2)
                    quality = self._calc_quality_score(latency, retry)
                    return {
                        "status": "有效",
                        "name": name,
                        "url": url,
                        "lat": latency,
                        "overseas": overseas,
                        "quality": quality,
                        "retries": retry
                    }
                
                if has_fatal:
                    break
                    
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
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain, 'Origin': domain}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        
        try:
            resp = self.session.head(url, headers=headers, timeout=10, allow_redirects=True, proxies=proxies)
            
            if resp.status_code in (200, 206, 301, 302, 304):
                latency = round(time.time() - start_time, 2)
                quality = self._calc_quality_score(latency, 0)
                return {"status": "有效", "name": name, "url": url, "lat": latency, "overseas": overseas, "quality": quality, "method": "HEAD"}
            
            elif resp.status_code == 405:
                resp = self.session.get(url, headers=headers, timeout=10, allow_redirects=True, proxies=proxies, stream=True)
                next(resp.iter_content(1024), None)
                resp.close()
                if resp.status_code in (200, 206, 301, 302, 304):
                    latency = round(time.time() - start_time, 2)
                    quality = self._calc_quality_score(latency, 0)
                    return {"status": "有效", "name": name, "url": url, "lat": latency, "overseas": overseas, "quality": quality, "method": "GET"}
            
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": f"HTTP {resp.status_code}"}
            
        except Exception as e:
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": f"HTTP检测失败: {e}"}
    
    def _calc_quality_score(self, latency: float, retries: int) -> int:
        if latency <= 1:
            latency_score = 60
        elif latency <= 3:
            latency_score = 50
        elif latency <= 5:
            latency_score = 40
        elif latency <= 10:
            latency_score = 20
        else:
            latency_score = 0
        
        retry_score = max(0, 40 - retries * 15)
        return min(100, latency_score + retry_score)


# ==================== 主应用类 ====================

class IPTVChecker:
    def __init__(self):
        self.logger = self._setup_logger()
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats = {'start_time': time.time(), 'total': 0, 'valid': 0, 'failed': 0, 
                     'by_category': defaultdict(int), 'by_overseas': {'cn': 0, 'overseas': 0}}
        Config.load_from_file()
    
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("IPTV_CHECK")
        logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)
        
        if logger.handlers:
            logger.handlers.clear()
        
        fh = logging.FileHandler(Config.LOG_FILE, encoding='utf-8', mode='w')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        fh.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)
        
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
            proc = subprocess.run(['ffprobe', '-version'], capture_output=True, timeout=10, shell=False)
            if proc.returncode != 0:
                self.logger.error("❌ 未找到 ffprobe，请安装 ffmpeg 并配置到系统 PATH")
                return False
            self.logger.info("✅ ffprobe 环境正常")
        except FileNotFoundError:
            self.logger.error("❌ 未找到 ffprobe，请安装 ffmpeg 并配置到系统 PATH")
            return False
        except Exception as e:
            self.logger.error(f"❌ ffprobe 检查异常: {e}")
            return False
        
        if input_file.exists():
            self.logger.info(f"✅ 本地输入文件正常: {input_file}")
        else:
            self.logger.warning(f"⚠️  本地输入文件不存在: {input_file}，将仅使用网络源")
        
        if Config.AUTO_BACKUP and output_file.exists():
            backup = output_file.parent / f"{output_file.stem}_backup_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            try:
                output_file.rename(backup)
                self.logger.info(f"✅ 上次结果已备份: {backup}")
            except Exception as e:
                self.logger.warning(f"⚠️  备份失败: {e}")
        
        self.logger.info("✅ 环境预检通过")
        self.logger.info("=" * 70)
        return True
    
    def read_local_file(self, input_file: Path) -> List[str]:
        if not input_file.exists():
            return []
        
        try:
            with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            
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
            self.logger.error(f"读取本地文件失败: {e}")
            return []
    
    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]) -> None:
        for line in lines:
            if ',' not in line:
                continue
            
            name_part, url_part = line.split(',', 1)
            url = url_part.strip()
            
            fp = URLCleaner.get_fingerprint(url)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            
            clean_name = NameProcessor.clean(name_part.strip())
            if not clean_name:
                continue
            
            host = urlparse(url).hostname or "unknown"
            domain_lines[host].append(f"{clean_name},{url}")
    
    def write_results(self, output_file: Path, cat_map: Dict[str, List[Dict[str, Any]]]) -> None:
        duration = time.time() - self.stats['start_time']
        
        buffer = []
        buffer.append(
            f"// 更新: {time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"有效 {self.stats['valid']}/{self.stats['total']} | "
            f"境内 {self.stats['by_overseas']['cn']} | "
            f"境外 {self.stats['by_overseas']['overseas']} | "
            f"未分类 {len(cat_map.get('其他頻道', []))}\n"
        )
        buffer.append(f"// 耗时: {duration:.1f}s\n\n")
        
        for cat in Config.CATEGORY_ORDER:
            items = cat_map.get(cat, [])
            if not items:
                continue
            
            buffer.append(f"{cat},#genre#\n")
            
            grouped = defaultdict(list)
            for item in items:
                if Config.ENABLE_QUALITY_FILTER and item.get('quality', 0) < Config.MIN_QUALITY_SCORE:
                    continue
                grouped[item['name']].append(item)
            
            # 特殊处理：央衛頻道 - CCTV频道按CCTV1-17排序，其他按延迟排序
            if cat == "央衛頻道":
                # 分离CCTV频道和其他频道
                cctv_channels = {}
                other_channels = {}
                
                for ch_name, items in grouped.items():
                    if ch_name.startswith('CCTV'):
                        # 提取CCTV数字编号
                        match = re.match(r'CCTV(\d+)', ch_name)
                        if match:
                            cctv_num = int(match.group(1))
                            cctv_channels[ch_name] = items
                        else:
                            other_channels[ch_name] = items
                    else:
                        other_channels[ch_name] = items
                
                # CCTV频道按1-17排序
                for cctv_num in range(1, 18):  # CCTV1-CCTV17
                    cctv_name = f"CCTV{cctv_num}"
                    if cctv_name in cctv_channels:
                        items = cctv_channels[cctv_name]
                        sorted_items = sorted(items, key=lambda x: (-x.get('quality', 0), x['lat']))
                        for item in sorted_items[:Config.MAX_LINKS_PER_NAME]:
                            buffer.append(f"{item['name']},{item['url']}\n")
                
                # CCTV+频道（如CCTV5+）
                if 'CCTV5+' in cctv_channels:
                    items = cctv_channels['CCTV5+']
                    sorted_items = sorted(items, key=lambda x: (-x.get('quality', 0), x['lat']))
                    for item in sorted_items[:Config.MAX_LINKS_PER_NAME]:
                        buffer.append(f"{item['name']},{item['url']}\n")
                
                # 其他卫视频道按延迟从低到高排序
                for ch_name in sorted(other_channels.keys(), key=lambda n: min(x['lat'] for x in other_channels[n])):
                    items = other_channels[ch_name]
                    sorted_items = sorted(items, key=lambda x: (-x.get('quality', 0), x['lat']))
                    for item in sorted_items[:Config.MAX_LINKS_PER_NAME]:
                        buffer.append(f"{item['name']},{item['url']}\n")
            
            else:
                # 其他分组：按延迟从低到高排序
                for ch_name in sorted(grouped.keys(), key=lambda n: min(x['lat'] for x in grouped[n])):
                    sorted_items = sorted(grouped[ch_name], key=lambda x: (-x.get('quality', 0), x['lat']))
                    
                    for item in sorted_items[:Config.MAX_LINKS_PER_NAME]:
                        buffer.append(f"{item['name']},{item['url']}\n")
            
            buffer.append("\n")
        
        # 原子写入
        tmp = output_file.with_suffix('.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(''.join(buffer))
            tmp.replace(output_file)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    
    def write_failures(self, fail_list: List[str]) -> None:
        if not (Config.ARCHIVE_FAIL and fail_list):
            return
        
        content = f"// 失效源 | {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(fail_list)} 条\n\n"
        content += "\n".join(fail_list) + "\n"
        
        tmp = Config.FAIL_FILE.with_suffix('.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(content)
            tmp.replace(Config.FAIL_FILE)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    
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
            self.logger.info(f"📊 统计信息已保存: {Config.STATS_FILE}")
        except Exception as e:
            self.logger.warning(f"⚠️ 保存统计信息失败: {e}")
    
    def run(self, args: argparse.Namespace) -> None:
        Config.DEBUG_MODE = args.debug or Config.DEBUG_MODE
        if args.proxy:
            Config.PROXY = args.proxy
        if args.timeout:
            Config.TIMEOUT_CN = args.timeout
        if args.workers:
            Config.MAX_WORKERS = args.workers
        
        if Config.DEBUG_MODE:
            self.logger = self._setup_logger()
        
        input_file = Path(args.input) if args.input else Config.INPUT_FILE
        output_file = Path(args.output) if args.output else Config.OUTPUT_FILE
        
        if not self.pre_check(input_file, output_file):
            sys.exit(1)
        
        seen_fp = set()
        domain_lines = defaultdict(list)
        
        self.logger.info("📂 读取本地文件...")
        local_lines = self.read_local_file(input_file)
        self.process_lines(local_lines, seen_fp, domain_lines)
        self.logger.info(f"✅ 本地文件处理完成，当前 {len(seen_fp)} 条")
        
        if Config.WEB_SOURCES and not args.no_web:
            self.logger.info(f"🌐 并发拉取 {len(Config.WEB_SOURCES)} 个网络源...")
            
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                future_to_url = {
                    executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                    for url in Config.WEB_SOURCES
                }
                
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        lines = future.result()
                        self.process_lines(lines, seen_fp, domain_lines)
                        self.logger.debug(f"✅ 拉取成功: {url} ({len(lines)}条)")
                    except Exception as e:
                        self.logger.error(f"❌ 拉取失败: {url} - {e}")
            
            self.logger.info(f"✅ 网络源拉取完成，当前 {len(seen_fp)} 条")
        
        lines_to_check = []
        for host_lines in domain_lines.values():
            random.shuffle(host_lines)
            lines_to_check.extend(host_lines)
        random.shuffle(lines_to_check)
        
        total = len(lines_to_check)
        if total == 0:
            self.logger.error("没有有效待测源，退出")
            return
        
        self.stats['total'] = total
        
        overseas_total = sum(1 for ln in lines_to_check if NameProcessor.is_overseas(ln.split(',', 1)[0]))
        cn_total = total - overseas_total
        self.logger.info(f"待测源: {total} 条 | 境内 {cn_total} | 境外 {overseas_total}")
        
        cat_map = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list = []
        
        real_workers = min(args.workers, total)
        self.logger.info(f"🚀 启动测活，并发: {real_workers}")
        
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="测活中", unit="源") as pbar:
            
            futures = {
                executor.submit(self.checker.check, ln, Config.PROXY): ln
                for ln in lines_to_check
            }
            
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
                        fail_list.append(f"{r['name']},{r['url']} | 原因: {r.get('reason', '未知')}")
                
                pbar.set_postfix({"有效率": f"{self.stats['valid'] / pbar.n * 100:.1f}%"})
        
        self.logger.info("💾 写入结果...")
        self.write_results(output_file, cat_map)
        self.write_failures(fail_list)
        self.write_stats()
        
        self.logger.info("=" * 70)
        self.logger.info(f"✅ 完成！结果保存至: {output_file}")
        self.logger.info(f"📊 整体有效率：{self.stats['valid']}/{self.stats['total']} = {self.stats['valid']/max(self.stats['total'], 1)*100:.1f}%")
        self.logger.info(f"🇨🇳 境内：{self.stats['by_overseas']['cn']}/{cn_total}")
        self.logger.info(f"🌍 境外：{self.stats['by_overseas']['overseas']}/{overseas_total}")
        self.logger.info(f"⏱️  耗时：{time.time() - self.stats['start_time']:.1f}秒")
        self.logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='IPTV直播源检测工具 - 终极版')
    parser.add_argument('--input', type=str, default=None, help='本地输入文件路径')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径')
    parser.add_argument('--workers', type=int, default=Config.MAX_WORKERS, help=f'并发检测线程数 (默认 {Config.MAX_WORKERS})')
    parser.add_argument('--proxy', type=str, default=None, help='HTTP/HTTPS 代理地址')
    parser.add_argument('--timeout', type=int, default=None, help='境内超时秒数 (默认 15)')
    parser.add_argument('--debug', action='store_true', help='开启调试输出')
    parser.add_argument('--no-web', action='store_true', help='跳过网络源拉取，仅检测本地文件')
    parser.add_argument('--no-quality-filter', action='store_true', help='关闭质量过滤')
    parser.add_argument('--min-quality', type=int, default=60, help='最小质量分数 (0-100, 默认 60)')
    
    args = parser.parse_args()
    
    if args.no_quality_filter:
        Config.ENABLE_QUALITY_FILTER = False
    else:
        Config.MIN_QUALITY_SCORE = args.min_quality
    
    checker = IPTVChecker()
    checker.run(args)


if __name__ == "__main__":
    main()
