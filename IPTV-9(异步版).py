import os, sys, re, time, json, random, argparse, warnings, asyncio
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict
from urllib.parse import urlparse
from functools import lru_cache
import requests
import zhconv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    FAIL_FILE = BASE_DIR / "live_fail.txt"
    LOG_FILE = BASE_DIR / "iptv_check.log"
    STATS_FILE = BASE_DIR / "stats.json"
    CONFIG_FILE = BASE_DIR / "config.json"
    
    ENABLE_WEB_FETCH = True
    ENABLE_WEB_CHECK = True
    ENABLE_LOCAL_CHECK = True
    SAVE_VALID_SOURCES = True
    AUTO_BACKUP = True
    ARCHIVE_FAIL = True
    AUTO_FETCH_SOURCES = True
    MAX_WORKERS = 80
    FETCH_WORKERS = 16
    TIMEOUT_CN = 5
    TIMEOUT_OVERSEAS = 8
    MAX_LINKS_PER_NAME = 3
    FILTER_PRIVATE_IP = True
    ENABLE_QUALITY_FILTER = True
    MIN_QUALITY_SCORE = 60
    PROXY = None
    MAX_URL_FINGERPRINTS = 30000
    MAX_NAME_SIMPLIFY = 20000
    
    BLACKLIST = {"购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", 
                 "教程", "联系", "推广", "免费"}
    OVERSEAS_KEYWORDS = {"TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
                         "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
                         "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
                         "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "beIN"}
    
    CATEGORY_RULES_COMPILED = {}
    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视"],
        "體育賽事": ["体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
                    "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "NBA", "英超", "西甲",
                    "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "CBA", "世界杯"],
        "音樂頻道": ["音乐", "歌", "MTV", "演唱会", "演唱", "点播", "KTV", "流行", "摇滚"],
        "少兒動漫": ["卡通", "动漫", "动画", "儿童", "少儿", "幼", "宝宝", "宝贝",
                    "炫动", "卡通片", "动漫片", "动画片", "CARTOON", "ANIME", "KIDS", "DISNEY"],
        "影視劇集": ["爱奇艺", "优酷", "腾讯视频", "芒果 TV", "剧集", "电影", "影院", "影视",
                    "电视剧", "NETFLIX", "网剧", "短剧", "港片", "台剧", "韩剧", "日剧", "美剧"],
        "港澳台頻": ["翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY",
                    "香港", "台湾", "澳门", "明珠", "无线", "NOW", "ESPN", "HBO"]
    }
    
    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]
    OVERSEAS_PREFIX = ['TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
                       'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠']
    
    WEB_SOURCES = [
        "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/lm317379829/PyramidStore/main/file/tv/live.txt",
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
    ]
    
    UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:109.0) Gecko/20100101 Firefox/119.0',
        'VLC/3.0.21 LibVLC/3.0.21',
    ]
    
    SAVEABLE_KEYS = {'ENABLE_WEB_FETCH', 'ENABLE_WEB_CHECK', 'ENABLE_LOCAL_CHECK', 'SAVE_VALID_SOURCES',
                     'AUTO_BACKUP', 'ARCHIVE_FAIL', 'AUTO_FETCH_SOURCES', 'MAX_WORKERS',
                     'FETCH_WORKERS', 'TIMEOUT_CN', 'TIMEOUT_OVERSEAS', 'MAX_LINKS_PER_NAME',
                     'FILTER_PRIVATE_IP', 'ENABLE_QUALITY_FILTER', 'MIN_QUALITY_SCORE',
                     'PROXY', 'WEB_SOURCES'}
    
    @classmethod
    def load_from_file(cls):
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for key, value in config.items():
                    if key in cls.SAVEABLE_KEYS and hasattr(cls, key):
                        setattr(cls, key, value)
                print(f"✅ 加载配置文件：{cls.CONFIG_FILE}")
            except Exception:
                print("⚠️ 加载配置文件失败，使用默认配置")
    
    @classmethod
    def save_to_file(cls):
        config_data = {}
        for key in cls.SAVEABLE_KEYS:
            if hasattr(cls, key):
                value = getattr(cls, key)
                if isinstance(value, (str, int, float, bool, list, dict)):
                    config_data[key] = value
        try:
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    @classmethod
    def init_compiled_rules(cls):
        for cat, keywords in cls.CATEGORY_RULES.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)


# ==================== 正则 & 工具类 ====================
class RegexPatterns:
    PRIVATE_IP = re.compile(r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|::1$|fc00:|fe80:|fd[0-9a-f]{2}:|localhost|0\.0\.0\.0)', re.IGNORECASE)
    EMOJI = re.compile(r'[\U00010000-\U0010ffff\U00002600-\U000027ff]+', re.UNICODE)
    CCTV_STANDARD = re.compile(r'CCTV\D?(\d{1,2})\s*\+?', re.IGNORECASE)
    NOISE = re.compile(r'(\(.*?\))|(\[.*?\])|【.*?】|《.*?》|<.*?>|{.*?}')
    SUFFIX = re.compile(r'(?i)[\-_~:.:\s|/\\]|HD|1080p|720p|360p|高清 | 超清 | 超高清 | 标清 | 直播 | 主线 | 台$')
    BLANK = re.compile(r'^[\s\-_~:.:·]+$')
    TVG_NAME = re.compile(r'tvg-name="([^"]+)"')
    DATE_TAG = re.compile(r'更新日期:.*')
    M3U_LINK = re.compile(r'https?://[^\s\'"<>]+(?:m3u|m3u8|txt)(?=[\s\'"<>]|$)', re.IGNORECASE)
    GITHUB_REPO = re.compile(r'github\.com/[\w-]+/[\w-]+')


class URLCleaner:
    _fingerprint_cache = {}
    
    @staticmethod
    def get_fingerprint(url: str) -> str:
        if url in URLCleaner._fingerprint_cache:
            return URLCleaner._fingerprint_cache[url]
        try:
            parsed = urlparse(url)
            fp = f"{parsed.hostname or ''}:{parsed.port or ''}{parsed.path}{parsed.query or ''}".lower()
        except:
            fp = url.lower()
        URLCleaner._fingerprint_cache[url] = fp
        if len(URLCleaner._fingerprint_cache) > 30000:
            URLCleaner._fingerprint_cache.clear()
        return fp
    
    @staticmethod
    def is_valid(url: str) -> bool:
        try:
            p = urlparse(url)
            return p.scheme in ('http', 'https') and bool(p.netloc)
        except:
            return False


class NameProcessor:
    _simplify_cache = {}
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def normalize_cctv(name: str) -> str:
        if not name or not name.upper().startswith('CCTV'):
            return name
        m = RegexPatterns.CCTV_STANDARD.search(name.upper())
        if not m:
            return name
        num = str(int(m.group(1)))
        return "CCTV5+" if num == "5" and "+" in name else f"CCTV{num}"
    
    @staticmethod
    def simplify(text: str) -> str:
        if not text:
            return ""
        if text in NameProcessor._simplify_cache:
            return NameProcessor._simplify_cache[text]
        result = RegexPatterns.NOISE.sub('', text)
        result = zhconv.convert(result, 'zh-hans').strip()
        NameProcessor._simplify_cache[text] = result
        if len(NameProcessor._simplify_cache) > 20000:
            NameProcessor._simplify_cache.clear()
        return result
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def clean(name: str) -> str:
        if not name:
            return "未知频道"
        n = RegexPatterns.EMOJI.sub('', name)
        n = RegexPatterns.NOISE.sub('', n)
        n = NameProcessor.normalize_cctv(n)
        n = RegexPatterns.SUFFIX.sub('', n)
        n = NameProcessor.simplify(n)
        n = NameProcessor.normalize_cctv(n)
        return "未知频道" if (not n or RegexPatterns.BLANK.match(n)) else n.strip()
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def get_category(name: str) -> str:
        s = NameProcessor.simplify(name)
        if any(kw in s for kw in Config.BLACKLIST):
            return "其他頻道"
        for cat in Config.CATEGORY_ORDER[:-1]:
            if Config.CATEGORY_RULES_COMPILED[cat].search(s):
                return cat
        return "其他頻道"
    
    @staticmethod
    @lru_cache(maxsize=8192)
    def is_overseas(name: str) -> bool:
        return any(kw.upper() in NameProcessor.simplify(name).upper() for kw in Config.OVERSEAS_KEYWORDS)


class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        parsed = []
        extinf = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF:'):
                extinf = line
                continue
            if extinf and ('http' in line):
                name = RegexPatterns.TVG_NAME.search(extinf)
                name = name.group(1).strip() if name else extinf.rsplit(',', 1)[-1].strip()
                name = RegexPatterns.DATE_TAG.sub('', name).strip() or '未知频道'
                parsed.append(f"{name},{line}")
                extinf = None
        return parsed


# ==================== 网络源获取 ====================
class WebSourceFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        adapter = requests.adapters.HTTPAdapter(pool_connections=Config.FETCH_WORKERS*2, pool_maxsize=Config.FETCH_WORKERS*3, max_retries=1)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    def fetch(self, url: str, proxy: Optional[str] = None) -> List[str]:
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Accept': 'text/plain,*/*'}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        timeout = (10, 60) if "githubusercontent" in url else (10, 30)
        
        try:
            resp = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=True, proxies=proxies, stream=True)
            resp.raise_for_status()
            lines = [chunk.decode('utf-8', errors='ignore').strip() for chunk in resp.iter_lines() if chunk]
            if any(l.startswith('#EXTM3U') for l in lines[:5]):
                return M3UParser.parse(lines)
            return self._parse_plain_text(lines)
        except Exception:
            raise
    
    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        parsed = []
        for line in lines:
            if ',' in line and '://' in line:
                name, url = line.split(',', 1)
                if URLCleaner.is_valid(url.strip()):
                    parsed.append(f"{name.strip()},{url.strip()}")
        return parsed


# ==================== 异步爬虫 ====================
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
            async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
                try:
                    r = await client.head(url)
                    return r.status_code < 400
                except:
                    return False
    
    async def _fetch_content(self, url: str) -> str:
        async with self.sem:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                try:
                    r = await client.get(url, timeout=12)
                    r.raise_for_status()
                    return r.text[:80000]
                except:
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
            except:
                continue
    
    async def validate_sources(self, sources: List[str]) -> Set[str]:
        print("  ✅ 异步验证源的有效性...")
        valid = set()
        async with httpx.AsyncClient(timeout=25, limits=httpx.Limits(max_connections=50)) as client:
            tasks = [self._validate_one(client, url) for url in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for url, ok in zip(sources, results):
                if isinstance(ok, bool) and ok:
                    valid.add(url)
        print(f"  📊 验证完成：有效 {len(valid)}/{len(sources)}")
        return valid
    
    async def _validate_one(self, client: httpx.AsyncClient, url: str) -> bool:
        try:
            r = await client.get(url, timeout=25)
            return r.status_code < 400 and len(r.text) > 100
        except:
            return False


# ==================== 流媒体检测 ====================
class StreamChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        adapter = requests.adapters.HTTPAdapter(pool_connections=Config.MAX_WORKERS*2, pool_maxsize=Config.MAX_WORKERS*3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        try:
            name, url = line.split(',', 1)
            name, url = name.strip(), url.strip()
            if not URLCleaner.is_valid(url):
                return {"status": "失效", "name": name, "url": url, "reason": "URL无效"}
            if Config.FILTER_PRIVATE_IP and RegexPatterns.PRIVATE_IP.match(urlparse(url).hostname or ""):
                return {"status": "失效", "name": name, "url": url, "reason": "内网"}
            
            overseas = NameProcessor.is_overseas(name)
            timeout = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN
            return self._http_check(url, name, timeout, proxy, overseas)
        except:
            return {"status": "失效", "name": "未知", "url": line, "reason": "解析失败"}
    
    def _http_check(self, url: str, name: str, timeout: int, proxy: Optional[str], overseas: bool) -> Dict[str, Any]:
        start = time.time()
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Connection': 'close'}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        
        try:
            r = self.session.head(url, headers=headers, timeout=(3, min(timeout, 4)), allow_redirects=True, proxies=proxies)
            if r.status_code in (200, 206, 301, 302, 304):
                lat = round(time.time() - start, 2)
                return {"status": "有效", "name": name, "url": url, "lat": lat, "overseas": overseas, "quality": self._score(lat)}
            
            r = self.session.get(url, headers=headers, timeout=(3, min(timeout, 4)), stream=True, proxies=proxies)
            if r.status_code in (200, 206):
                lat = round(time.time() - start, 2)
                r.close()
                return {"status": "有效", "name": name, "url": url, "lat": lat, "overseas": overseas, "quality": self._score(lat)}
            return {"status": "失效", "name": name, "url": url, "reason": f"HTTP{r.status_code}"}
        except (requests.Timeout, requests.ConnectTimeout):
            return {"status": "失效", "name": name, "url": url, "reason": "超时"}
        except Exception as e:
            return {"status": "失效", "name": name, "url": url, "reason": str(type(e).__name__)[:12]}
    
    @staticmethod
    def _score(lat: float) -> int:
        if lat <= 1: return 100
        if lat <= 3: return 80
        if lat <= 5: return 60
        if lat <= 10: return 40
        return 20


# ==================== 主检测器 ====================
class IPTVChecker:
    def __init__(self):
        Config.init_compiled_rules()
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats = {'start_time': time.time(), 'total': 0, 'valid': 0, 'failed': 0,
                      'by_category': defaultdict(int), 'by_overseas': {'cn': 0, 'overseas': 0}}
        Config.load_from_file()
    
    def pre_check(self, input_file: Path, output_file: Path) -> bool:
        print("=" * 70)
        print("🔍 开始环境预检...")
        if input_file.exists():
            print(f"✅ 本地文件：{input_file}")
        if Config.AUTO_BACKUP and output_file.exists():
            backup = output_file.parent / f"{output_file.stem}_backup_{int(time.time())}.txt"
            try:
                output_file.rename(backup)
                print(f"✅ 已备份到 {backup}")
            except:
                pass
        print("=" * 70)
        return True
    
    def read_local_file(self, input_file: Path) -> List[str]:
        if not input_file.exists():
            return []
        with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = [l.strip() for l in f if l.strip()]
        return M3UParser.parse(lines) if any(l.startswith('#EXTM3U') for l in lines[:5]) else [
            f"{p[0].strip()},{p[1].strip()}" for line in lines if ',' in line and '://' in line
            for p in [line.split(',', 1)] if URLCleaner.is_valid(p[1].strip())
        ]
    
    def process_lines(self, lines: List[str], seen: Set[str], domain_lines: Dict[str, List[str]]):
        for line in lines:
            if ',' not in line:
                continue
            name_part, url = line.split(',', 1)
            url = url.strip()
            fp = URLCleaner.get_fingerprint(url)
            if fp not in seen:
                seen.add(fp)
                clean_name = NameProcessor.clean(name_part.strip())
                if clean_name:
                    host = urlparse(url).hostname or "unknown"
                    domain_lines[host].append(f"{clean_name},{url}")
    
    def write_results(self, output_file: Path, cat_map: Dict):
        duration = time.time() - self.stats['start_time']
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"// 更新：{time.strftime('%Y-%m-%d %H:%M:%S')} | 有效 {self.stats['valid']}/{self.stats['total']} | 耗时 {duration:.1f}s\n\n")
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
                    self._write_cctv(f, grouped)
                else:
                    self._write_normal(f, grouped)
                f.write("\n")
    
    def _write_cctv(self, f, grouped):
        cctv, other = {}, {}
        for n, lst in grouped.items():
            (cctv if n.startswith('CCTV') else other)[n] = lst
        for i in range(1, 18):
            if f"CCTV{i}" in cctv:
                for item in sorted(cctv[f"CCTV{i}"], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                    f.write(f"{item['name']},{item['url']}\n")
        if 'CCTV5+' in cctv:
            for item in sorted(cctv['CCTV5+'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")
        for n in sorted(other):
            for item in sorted(other[n], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")
    
    def _write_normal(self, f, grouped):
        for n in sorted(grouped):
            for item in sorted(grouped[n], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                f.write(f"{item['name']},{item['url']}\n")
    
    def run(self, args):
        if args.proxy: Config.PROXY = args.proxy
        if args.timeout:
            Config.TIMEOUT_CN = args.timeout
            Config.TIMEOUT_OVERSEAS = int(args.timeout * 1.5)
        if args.workers:
            Config.MAX_WORKERS = args.workers
        
        input_file = Path(args.input) if args.input else Config.INPUT_FILE
        output_file = Path(args.output) if args.output else Config.OUTPUT_FILE
        
        if not self.pre_check(input_file, output_file):
            sys.exit(1)
        
        seen_fp = set()
        domain_lines = defaultdict(list)
        
        if Config.ENABLE_LOCAL_CHECK:
            print("📂 读取本地文件...")
            self.process_lines(self.read_local_file(input_file), seen_fp, domain_lines)
            print(f"✅ 本地处理完成：{len(seen_fp)}条")
        
        web_sources = set(Config.WEB_SOURCES)
        
        if Config.ENABLE_WEB_FETCH and Config.AUTO_FETCH_SOURCES and not args.no_web and not args.no_fetch:
            print("🕷️ 异步爬取网页源（asyncio + httpx）...")
            crawler = AsyncWebSourceCrawler()
            start = time.time()
            new_sources = asyncio.run(crawler.crawl())
            web_sources = set(Config.WEB_SOURCES) | new_sources
            print(f"🕷️ 爬取完成：新增{len(new_sources)}个 | 总计{len(web_sources)}个 | 耗时{time.time()-start:.1f}s")
            
            print("🔍 异步验证源的有效性...")
            valid = asyncio.run(crawler.validate_sources(list(web_sources)))
            if Config.SAVE_VALID_SOURCES and valid:
                Config.WEB_SOURCES = list(valid)
                Config.save_to_file()
        
        if Config.ENABLE_WEB_CHECK and web_sources and not args.no_web:
            print(f"🌐 拉取 {len(web_sources)} 个网络源...")
            web_success = web_total = 0
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as ex:
                fs = {ex.submit(self.fetcher.fetch, u, Config.PROXY): u for u in web_sources}
                for f in as_completed(fs):
                    try:
                        lines = f.result(timeout=90)
                        web_success += 1
                        web_total += len(lines)
                        self.process_lines(lines, seen_fp, domain_lines)
                    except:
                        pass
            print(f"🌐 网络源汇总：成功{web_success}个 | 获得{web_total}条 | 去重后{len(seen_fp)}条")
        
        lines_to_check = [ln for lst in domain_lines.values() for ln in lst]
        random.shuffle(lines_to_check)
        total = len(lines_to_check)
        if total == 0:
            print("没有待测源")
            return
        
        self.stats['total'] = total
        print(f"待测：{total}条")
        
        cat_map = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list = []
        
        with ThreadPoolExecutor(max_workers=min(args.workers, total)) as ex, \
             tqdm(total=total, desc="测活中", unit="源", ncols=80) as pbar:
            fs = {ex.submit(self.checker.check, ln, Config.PROXY): ln for ln in lines_to_check}
            for f in as_completed(fs):
                try:
                    r = f.result(timeout=Config.TIMEOUT_OVERSEAS + 6)
                    pbar.update(1)
                    if r["status"] == "有效":
                        self.stats['valid'] += 1
                        cat = NameProcessor.get_category(r["name"])
                        if cat in cat_map:
                            cat_map[cat].append(r)
                    else:
                        self.stats['failed'] += 1
                        if Config.ARCHIVE_FAIL:
                            fail_list.append(f"{r.get('name','未知')},{r.get('url','')} | {r.get('reason','')}")
                except:
                    pbar.update(1)
                    self.stats['failed'] += 1
        
        self.write_results(output_file, cat_map)
        if Config.ARCHIVE_FAIL and fail_list:
            with open(Config.FAIL_FILE, 'w', encoding='utf-8') as f:
                f.write(f"// 失效源 | {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(fail_list)}条\n\n" + "\n".join(fail_list))
        
        duration = time.time() - self.stats['start_time']
        print("=" * 70)
        print(f"✅ 完成！有效 {self.stats['valid']}/{total} = {self.stats['valid']/total*100:.1f}%")
        print(f"⏱️  耗时：{duration:.1f}秒")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具（2026 异步版）')
    parser.add_argument('--input', type=str)
    parser.add_argument('--output', type=str)
    parser.add_argument('--workers', type=int, default=Config.MAX_WORKERS)
    parser.add_argument('--proxy', type=str)
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--no-web', action='store_true')
    parser.add_argument('--no-fetch', action='store_true')
    parser.add_argument('--no-local', action='store_true')
    parser.add_argument('--no-web-check', action='store_true')
    parser.add_argument('--no-quality-filter', action='store_true')
    parser.add_argument('--min-quality', type=int, default=60)
    args = parser.parse_args()
    
    if args.no_fetch: Config.ENABLE_WEB_FETCH = False
    if args.no_local: Config.ENABLE_LOCAL_CHECK = False
    if args.no_web_check: Config.ENABLE_WEB_CHECK = False
    if args.no_quality_filter: Config.ENABLE_QUALITY_FILTER = False
    else: Config.MIN_QUALITY_SCORE = args.min_quality
    
    IPTVChecker().run(args)


if __name__ == "__main__":
    main()