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
    ENABLE_WEB_FETCH    = False  # 是否启用自动爬取新增网络直播源的功能
    ENABLE_WEB_CHECK    = False  # 是否启用拉取并检测预设网络源的功能（默认开启）
    ENABLE_LOCAL_CHECK  = True   # 是否启用读取并检测本地输入文件的功能
    ENABLE_SPEED_CHECK  = True   # 是否启用下载速度检测
    DEBUG_MODE          = False  # 调试模式开关
    AUTO_BACKUP         = True   # 自动备份开关（备份文件名含时间戳）
    ARCHIVE_FAIL        = True   # 失效源归档开关

    # 性能与超时配置
    MAX_WORKERS         = 64     # 直播源检测的最大并发线程数
    FETCH_WORKERS       = 4      # 网络源拉取的最大并发线程数
    TIMEOUT_CN          = 12     # 境内直播源检测超时时间（秒）
    TIMEOUT_OVERSEAS    = 24     # 境外直播源检测超时时间（秒）
    RETRY_COUNT         = 2      # 网络请求重试次数
    REQUEST_JITTER      = False  # 请求抖动开关
    MAX_LINKS_PER_NAME  = 3      # 每个频道保留的最大有效链接数
    MAX_SOURCES_PER_DOMAIN = 0   # 每个域名最多保留的源数量（0=不限制）

    # 过滤与质量配置
    FILTER_PRIVATE_IP       = True   # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False  # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER   = True   # 质量过滤开关
    MIN_QUALITY_SCORE       = 15     # 修复：降低默认阈值，适配大部分有效源
    MIN_SPEED_MBPS          = 0.005   # 最低下载速度阈值（MB/s），低于此值直接判定失效
    SPEED_CHECK_BYTES       = 32768  # 速度检测下载字节数（32KB）

    # IPv6 优化配置
    ENABLE_IPV6_OPTIMIZE    = True   # 是否启用 IPv6 优化（IPv6 地址直接判定有效并给予高分）
    IPV6_DEFAULT_DELAY      = 0.1    # IPv6 默认延迟（秒）
    IPV6_DEFAULT_SPEED      = 10.0   # IPv6 默认速度（MB/s）

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
        'SPEED_CHECK_BYTES', 'ENABLE_IPV6_OPTIMIZE', 'IPV6_DEFAULT_DELAY',
        'IPV6_DEFAULT_SPEED'
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

    # 直播源致命错误关键词
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
        "405 method not allowed", "forbidden", "not found"
    }

    # 频道分类规则（优先级按CATEGORY_ORDER顺序）
    CATEGORY_RULES_COMPILED: Dict = {}
    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR", "杜比视界"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视", "CETV", "中国教育", "兵团", "农林"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "咪咕", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J 联赛", "K 联赛", "美职",
            "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
            "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运", "文体",
            "亚运", "世界杯", "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA", "五大联赛", "Pac-12"
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼", "宝宝", "宝贝",
            "炫动", "卡通片", "动漫片", "动画片", "CARTOON", "ANIME", "ANIMATION",
            "KIDS", "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS",
            "TOON", "BOOMERANG", "尼克", "小公视", "蓝猫", "喜羊羊", "熊出没", "萌鸡小队"
        ],
        "音樂頻道": [
            "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV",
            "流行", "嘻哈", "摇滚", "古典", "爵士", "民谣", "电音", "EDM",
            "纯音乐", "伴奏", "Karaoke", "Channel V", "Trace", "VH1", "MTV Hits",
            "MTV Live", "KKBOX", "女团", "Space Shower", "KAYOPOPS", "Musicon", "音悦台"
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
            "华影", "金鹰", "星河", "新视觉", "哔哩哔哩", "B站", "西瓜视频",
            "搜狐视频", "乐视", "PP视频", "聚力", "风行", "暴风影音", "欢喜首映",
            "南瓜电影", "独播剧场", "黄金剧场", "首播剧场", "院线大片", "经典电影",
            "华语电影", "欧美电影", "日韩电影", "付费点播", "VIP影院", "家庭影院",
            "动作电影", "喜剧电影", "爱情电影", "科幻电影", "恐怖电影", "纪录片",
            "微电影", "网络大电影", "影城", "影厅", "首映", "点播影院"
        ],
        "港澳台頻": [
            "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理",
            "香港", "华文", "八度", "华艺", "环球", "生命", "镜", "澳", "台湾", "探索",
            "年代", "明珠", "唯心", "公视", "东森", "三立", "爱尔达", "NOW", "VIU",
            "STAR", "星空", "纬来", "非凡", "中天", "中视", "无线", "寰宇", "Z频道",
            "GOOD", "ROCK", "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天",
            "AXN", "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "奇妙电视", "香港开电视", "有线宽频", "ViuTVsix", "ViuTVtwo", "澳广视",
            "TDM", "澳门卫视", "壹电视", "CTI", "CTS", "PTS", "NTV", "Fuji TV",
            "NHK", "TBS", "WOWOW", "Sky", "ESPN", "beIN", "DAZN", "Eleven Sports",
            "SPOTV NOW", "TrueVisions", "Astro", "Unifi TV", "HyppTV", "myTV SUPER",
            "Now TV", "Cable TV", "PCCW", "HKTV", "Viu", "Netflix", "Disney+", "RHK",
            "TTV", "FTV", "TRANSTV", "TLC", "SURIA", "SUPERFREE", "SUNTV", "SUNEWS",
            "SUMUSIC", "SULIF", "SUKART", "SPOT2", "SPOT", "SONYTEN3", "SET 新闻",
            "RTV", "ROCKACTION", "RIA", "QJ", "OKEY", "NET", "MTLIVE", "猪王", "华仁",
            "宏达", "卫视中文", "卫视电影", "卫视音乐", "年代新闻", "东森新闻",
            "中天新闻", "民视新闻", "台视新闻", "华视新闻", "三立新闻", "非凡新闻",
            "TVBS新闻", "凤凰卫视资讯台", "凤凰卫视中文台", "凤凰卫视香港台",
            "中天亚洲", "东森亚洲"
        ],
        "其他頻道": []
    }
    CATEGORY_ORDER = ["4K 專區", "央衛頻道", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]

    # 预设网络源列表（统一管理，避免重复拉取）
    WEB_SOURCES = []  # 成功拉取的网页源
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
        "https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1",
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://raw.githubusercontent.com/yuanzl77/IPTV/master/live.txt",
        "https://iptv-org.github.io/iptv/countries/mo.m3u",
        "https://iptv-org.github.io/iptv/index.m3u"
    ]

    # IPTV播放器专用UA池
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

    # ✅ 点播域名黑名单（短视频/点播平台域名，非直播源）
    VOD_DOMAINS = {
        # 百度系短视频
        "vd2.bdstatic.com", "vd3.bdstatic.com", "vd4.bdstatic.com", "vdse.bdstatic.com",
        # 抖音/快手系
        "www.iesdouyin.com", "jsmov2.a.yximgs.com", "txmov2.a.kwimgs.com", "alimov2.a.kwimgs.com",
        # 淘宝系
        "cloud.video.taobao.com", "vodcdn.video.taobao.com",
        # 京东系
        "php.jdshipin.com:2096", "r.jdshipin.com", "cdn.jdshipin.com",
        # 蜻蜓FM
        "ls.qingting.fm", "lhttp.qingting.fm",
        # 酷我音乐
        "mobi.kuwo.cn", "vdown.kuwo.cn", "vdown2.kuwo.cn",
        # 搜狐
        "tv.sohu.blog", "ah2.sohu.blog:8000",
        # 阿里系CDN
        "bizcommon.alicdn.com", "lvbaiducdnct.inter.ptqy.gitv.tv",
    }

    # ✅ 直播频道名关键词（用于识别真正的直播频道，区分点播内容）
    LIVE_CHANNEL_KEYWORDS = re.compile(
        r'频道|台|卫视|影院|剧场|电影|剧集|直播|体育|音乐|新闻|综合|少儿|动漫|教育|财经|'
        r'Discovery|Channel|TV|News|Live|Sport|Music|Kids|Movie|Film|Drama|Anime'
    )

    @classmethod
    def init_compiled_rules(cls):
        """初始化时预编译分类正则表达式，提升匹配效率"""
        for cat, keywords in cls.CATEGORY_RULES.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)

    @classmethod
    def load_from_file(cls):
        """白名单机制加载配置，缺失字段保留默认值"""
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
            else:
                print(f"✅ 加载配置文件：{cls.CONFIG_FILE}（使用默认值）")
        except Exception as e:
            print(f"⚠️ 加载配置文件失败：{e}，使用默认配置")

    @classmethod
    def save_to_file(cls, web_sources: List[str]):
        """保存成功的网页源到配置文件"""
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

# 初始化预编译正则，确保调用时已存在
Config.init_compiled_rules()

# ==================== 正则表达式预编译（全局复用，提升性能） ====================
class RegexPatterns:
    PRIVATE_IP = re.compile(
        r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|'
        r'::1$|fc00:|fe80:|fd[0-9a-f]{2}:|localhost|0\.0\.0\.0)',
        re.IGNORECASE
    )
    DATE_TAG      = re.compile(r'\[.*?\]|\(.*?\)|【.*?】|\{.*?\}', re.IGNORECASE)
    TVG_NAME      = re.compile(r'tvg-name="([^"]+)"')
    TVG_LOGO      = re.compile(r'tvg-logo="([^"]+)"')
    GROUP_TITLE   = re.compile(r'group-title="([^"]+)"')
    CCTV_FIND     = re.compile(r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)')
    CCTV_STANDARD = re.compile(r'CCTV\D*?(\d{1,2})\s*(\+?)', re.IGNORECASE)
    EMOJI         = re.compile(
        r'[\U00010000-\U0010ffff\U00002600-\U000027ff\U0000f600-\U0000f6ff'
        r'\U0000f300-\U0000f3ff\U00002300-\U000023ff\U00002500-\U000025ff'
        r'\U00002100-\U000021ff\U000000a9\U000000ae\U00002000-\U0000206f'
        r'\U00002460-\U000024ff\U00001f00-\U00001fff]+',
        re.UNICODE
    )
    NOISE         = re.compile(r'\(.*?\)|\)|\[.*?\]|【.*?】|《.*?》|<.*?>|\{.*\}')
    HIRES         = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清|杜比视界')
    SUFFIX        = re.compile(
        r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|540p|高清|超清|超高清|标清|直播|主线|备用|线路'
    )
    BLANK         = re.compile(r'^[\s\-—_～•·:·]+$')
    M3U_EXTINF    = re.compile(r'^#EXTINF:-?\d+(.*?),', re.IGNORECASE)

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

# ==================== 修复：同步下载速度检测（彻底解决多线程事件循环冲突） ====================
def get_speed_with_download(url: str, timeout: int = 5) -> float:
    """
    下载前N KB数据计算真实下载速度（同步实现，线程安全）
    :param url: 直播源地址
    :param timeout: 超时时间（秒）
    :return: 下载速度 MB/s，失败返回 0.0
    """
    try:
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        }
        start_time = time.time()
        downloaded_bytes = 0

        with requests.Session() as session:
            with session.get(
                url, headers=headers, timeout=timeout,
                verify=False, allow_redirects=True, stream=True
            ) as resp:
                if resp.status_code not in (200, 206):
                    return 0.0
                # 仅读取指定字节数，避免全量下载
                for chunk in resp.iter_content(chunk_size=1024):
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes >= Config.SPEED_CHECK_BYTES:
                        break
                # 计算速度（MB/s）
                elapsed = time.time() - start_time
                if elapsed <= 0 or downloaded_bytes < 1024:
                    return 0.0
                speed_mbps = (downloaded_bytes / 1024 / 1024) / elapsed
                return round(speed_mbps, 2)
    except Exception:
        return 0.0

# ==================== URL 清理器 ====================
class URLCleaner:
    @staticmethod
    @lru_cache(maxsize=10000)
    def get_fingerprint(url: str) -> str:
        """URL 指纹提取（带缓存），用于去重"""
        parsed = urlparse(url)
        if Config.REMOVE_REDUNDANT_PARAMS:
            keep_params = {'id', 'token', 'key', 'sign', 'auth', 'code', 'streamid'}
            query_dict = {k: v for k, v in parse_qs(parsed.query).items()
                          if k.lower() in keep_params}
            query_str = urlencode(query_dict, doseq=True) if query_dict else ''
        else:
            query_str = parsed.query
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_str}"

    @staticmethod
    def is_valid(url: str) -> bool:
        """URL 有效性基础检查"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https', 'rtmp', 'rtmps', 'rtsp') and bool(parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        """内网IP过滤，返回 True 表示可用"""
        if not Config.FILTER_PRIVATE_IP:
            return True
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return not RegexPatterns.PRIVATE_IP.match(hostname)

    @staticmethod
    def is_ipv6(url: str) -> bool:
        """✅ 检测是否为 IPv6 地址（URL 中的 IPv6 一定是 [::1] 格式）"""
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return hostname.startswith('[')

    @staticmethod
    def is_vod_domain(url: str) -> bool:
        """✅ 检测是否为点播域名（短视频/点播平台）"""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # 完全匹配或子域名匹配
        for vod_domain in Config.VOD_DOMAINS:
            if vod_domain in netloc or netloc.endswith(vod_domain.split(':')[0]):
                return True
        return False

# ==================== M3U 解析器 ====================
class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        """优先提取 tvg-name，回退到逗号后取名，提升频道名准确率"""
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
                    # 优先提取 tvg-name
                    m = RegexPatterns.TVG_NAME.search(extinf_line)
                    if m:
                        name_part = m.group(1).strip()
                    else:
                        # 回退到逗号后的名称
                        name_split = extinf_line.split(',', 1)
                        name_part = name_split[-1].strip() if len(name_split) > 1 else '未知频道'
                    # 清理日期标签与空值
                    name_part = RegexPatterns.DATE_TAG.sub('', name_part).strip() or '未知频道'
                    parsed.append(f"{name_part},{line}")
                    extinf_line = None
        return parsed

    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        """纯文本格式解析（name,url）"""
        parsed = []
        for line in lines:
            if ',' not in line or '://' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            url_part = url_part.strip()
            if URLCleaner.is_valid(url_part):
                parsed.append(f"{name_part.strip()},{url_part}")
        return parsed

# ==================== 网络源获取器 ====================
class WebSourceFetcher:
    """网络源获取器 - 单例 + 连接池复用"""
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
        # 连接池优化，适配FETCH_WORKERS
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.FETCH_WORKERS * 2,
            pool_maxsize=Config.FETCH_WORKERS * 2,
            max_retries=1,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    @retry(max_attempts=2, delay=0.5, backoff=2)
    def fetch(self, url: str, proxy: Optional[str] = None) -> List[str]:
        """网络源拉取，优化编码处理避免乱码"""
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
            resp = self.session.get(
                url, headers=headers, timeout=timeout,
                allow_redirects=True, proxies=proxies, stream=False
            )
            resp.raise_for_status()
            # 优化编码处理：优先UTF-8，失败再用自动识别
            try:
                text = resp.content.decode('utf-8')
            except UnicodeDecodeError:
                resp.encoding = resp.apparent_encoding or 'gbk'
                text = resp.text
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines:
                return []
            # 自动识别M3U格式并解析
            parsed = M3UParser.parse(lines) if any(l.startswith('#EXTM3U') for l in lines[:10]) \
                     else M3UParser._parse_plain_text(lines)
            # 指纹去重
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

# ==================== 异步网络源爬虫 ====================
class AsyncWebSourceCrawler:
    """异步爬虫 - 多源聚合爬取，优化有效性校验与去重"""
    @property
    def SOURCE_SITES(self):
        return Config.PRESET_FILES
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
        timeout = httpx.Timeout(8.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30, keepalive_expiry=15.0)
        self.session = httpx.AsyncClient(timeout=timeout, limits=limits, verify=False, follow_redirects=True)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 1.5) -> bool:
        """优化：HEAD请求失败自动降级GET，避免405误判"""
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        }
        try:
            # 优先HEAD请求，快速校验
            resp = await self.session.head(url, headers=headers, timeout=timeout, follow_redirects=True)
            if resp.status_code in (200, 206, 301, 302, 304):
                return True
            # HEAD失败，降级GET请求，仅读取前1024字节
            async with self.session.stream('GET', url, headers=headers, timeout=timeout) as resp:
                if resp.status_code in (200, 206):
                    await resp.aread(1024)
                    return True
            return False
        except Exception:
            return False

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        """从页面内容中提取直播源，深度限制避免无限递归"""
        if depth > 1:
            return set()
        try:
            headers = {
                'User-Agent': random.choice(Config.UA_POOL),
                'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            }
            resp = await self.session.get(url, headers=headers, timeout=8.0)
            if resp.status_code != 200 or not resp.text or len(resp.text) < 10:
                return set()
            # 正则匹配所有符合规则的URL
            all_matches: Set[str] = set()
            for pattern in self.URL_PATTERNS:
                all_matches.update(re.findall(pattern, resp.text, re.IGNORECASE))
            valid_sources: Set[str] = set()
            semaphore = asyncio.Semaphore(30)

            async def validate_and_add(source: str):
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
            # 批量并发校验
            batch_size = 50
            for i in range(0, len(all_matches), batch_size):
                await asyncio.gather(*[validate_and_add(s) for s in list(all_matches)[i:i+batch_size]],
                                     return_exceptions=True)
            # 递归深度1的子页面爬取
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
        """爬取并返回 {子url: 域名} 映射，用域名作频道名"""
        async with semaphore:
            try:
                parsed_url = urlparse(url)
                base_domain = parsed_url.netloc.split(':')[0]
                if not await self.quick_validate(url, timeout=2.0):
                    return {}
                extracted = await self.extract_sources_from_content(url)
                if not extracted:
                    return {}
                return {sub_url: base_domain for sub_url in extracted}
            except Exception:
                return {}

    async def crawl_all_with_names(self) -> Dict[str, str]:
        """爬取并返回带名称的源映射"""
        print("🔍 开始异步爬取网络源...")
        semaphore = asyncio.Semaphore(10)
        tasks = [self.crawl_single_source_with_name(url, semaphore) for url in self.SOURCE_SITES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        url_to_name = {}
        for r in results:
            if isinstance(r, dict):
                url_to_name.update(r)
        print(f"✅ 爬取完成: 发现新源 {len(url_to_name)} 个")
        return url_to_name

# ==================== 直播源检测器 ====================
class StreamChecker:
    """直播源检测器 - 单例 + 连接池复用，修复速度检测逻辑"""
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
        # 测活专用连接池，快速失败不重试
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.MAX_WORKERS * 2,
            pool_maxsize=Config.MAX_WORKERS * 2,
            max_retries=0,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def check(self, line: str, proxy: Optional[str] = None) -> Dict[str, Any]:
        """检测单条直播源，修复速度检测与质量评分逻辑，新增 IPv6 优化"""
        if ',' not in line:
            return {"status": "失效", "name": "未知频道", "url": line, "overseas": False}
        try:
            name_part, url_part = line.split(',', 1)
            url  = url_part.strip()
            name = name_part.strip()[:100]

            # 基础有效性过滤
            if not URLCleaner.is_valid(url):
                return {"status": "失效", "name": name, "url": url, "overseas": False, "reason": "URL无效"}
            if not URLCleaner.filter_private_ip(url):
                return {"status": "失效", "name": name, "url": url, "overseas": False, "reason": "内网IP"}
            if any(kw in name for kw in Config.BLACKLIST):
                return {"status": "失效", "name": name, "url": url, "overseas": False, "reason": "黑名单关键词"}

            # ✅ IPv6 优化：直接返回高分（IPv6 地址通常更稳定）
            if Config.ENABLE_IPV6_OPTIMIZE and URLCleaner.is_ipv6(url):
                overseas = NameProcessor.is_overseas(name)
                return {
                    "status": "有效", "name": name, "url": url,
                    "lat": Config.IPV6_DEFAULT_DELAY,
                    "speed": Config.IPV6_DEFAULT_SPEED,
                    "overseas": overseas,
                    "quality": 100,  # IPv6 直接满分
                    "ipv6": True
                }

            # 境外源匹配与超时设置
            overseas = NameProcessor.is_overseas(name)
            timeout  = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN

            # 请求抖动
            if Config.REQUEST_JITTER:
                time.sleep(random.uniform(0.01, 0.05))

            # 优先ffprobe检测（最准确）
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)
            # 失败则降级HTTP检测
            if not result:
                result = self._check_with_http(url, name, timeout, proxy, overseas)
            # 有效源执行速度检测
            if result["status"] == "有效" and Config.ENABLE_SPEED_CHECK:
                speed_mbps = get_speed_with_download(url, timeout=min(timeout, 5))
                result["speed"] = speed_mbps
                # 低于最低速度阈值直接判定失效
                if speed_mbps < Config.MIN_SPEED_MBPS:
                    result["status"] = "失效"
                    result["reason"] = f"速度不足{speed_mbps}MB/s"
                else:
                    # 双维度质量评分
                    result["quality"] = self._calc_quality_score(result["lat"], speed_mbps)
            # 修复：速度检测关闭时，用延迟单独评分
            elif result["status"] == "有效" and not Config.ENABLE_SPEED_CHECK:
                result["speed"] = 0.0
                result["quality"] = self._calc_quality_score(result["lat"], 1.0)  # 速度兜底满分
            return result
        except Exception as e:
            return {"status": "失效", "name": "未知频道", "url": line, "reason": str(e)[:30]}

    def _check_with_ffprobe(self, url: str, name: str, timeout: int,
                            proxy: Optional[str], overseas: bool) -> Optional[Dict[str, Any]]:
        """ffprobe流检测，优化冗余UA设置，提升兼容性"""
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        # 统一请求头，包含UA与Referer
        headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\n'
        cmd = [
            'ffprobe', '-headers', headers_str, '-v', 'error',
            '-show_entries', 'stream=codec_type:format=duration,format_name',
            '-probesize', '5000000', '-analyzeduration', '10000000',
            '-timeout', str(int(timeout * 1_000_000)), '-reconnect', '1',
            '-reconnect_streamed', '1', '-reconnect_delay_max', '2',
            '-err_detect', 'ignore_err', '-fflags', 'nobuffer+flush_packets',
        ]
        # 代理设置
        if proxy:
            cmd.extend(['-http_proxy', proxy])
        cmd.append(url)

        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            stdout, stderr = proc.communicate(timeout=timeout + 2)
            stdout_text = stdout.decode('utf-8', errors='ignore').lower()
            stderr_text = stderr.decode('utf-8', errors='ignore').lower()

            # 致命错误检测
            has_fatal  = any(kw in stderr_text for kw in Config.FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_text or 'codec_type=audio' in stdout_text

            if not has_fatal and has_stream:
                latency = round(time.time() - start_time, 2)
                return {
                    "status": "有效", "name": name, "url": url, "lat": latency,
                    "overseas": overseas, "quality": 0, "speed": 0.0
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
        """HTTP fallback检测，优化HEAD+GET双校验，避免405误判"""
        start_time = time.time()
        domain  = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        http_timeout = timeout // 2

        try:
            # 优先HEAD请求
            resp = self.session.head(
                url, headers=headers, timeout=http_timeout,
                allow_redirects=True, proxies=proxies
            )
            # 无论成功失败都需要关闭连接
            resp.close()
            
            if resp.status_code not in (200, 206, 301, 302, 304):
                # HEAD失败，降级GET请求，仅读取前1024字节
                resp = self.session.get(
                    url, headers=headers, timeout=http_timeout,
                    allow_redirects=True, proxies=proxies, stream=True
                )
                if resp.status_code not in (200, 206):
                    return {
                        "status": "失效", "name": name, "url": url, "overseas": overseas,
                        "reason": f"HTTP{resp.status_code}"
                    }
                resp.close()
            # 计算延迟与返回结果
            latency = round(time.time() - start_time, 2)
            return {
                "status": "有效", "name": name, "url": url, "lat": latency,
                "overseas": overseas, "quality": 0, "speed": 0.0
            }
        except Exception:
            return {
                "status": "失效", "name": name, "url": url, "overseas": overseas,
                "reason": "检测超时/连接失败"
            }

    @staticmethod
    def _calc_quality_score(latency: float, speed_mbps: float) -> int:
        """双维度质量评分：延迟+速度，满分100（宽松版，适配影视仓）"""
        # 延迟基础分（60分权重）—— 放宽到15秒都给分
        base_score = 0
        if latency <= 1:
            base_score = 60
        elif latency <= 3:
            base_score = 50
        elif latency <= 5:
            base_score = 40
        elif latency <= 10:
            base_score = 30
        elif latency <= 15:
            base_score = 20
        else:
            base_score = 10

        # 速度附加分（40分权重）—— 大幅放宽速度门槛
        speed_score = 0
        if speed_mbps >= 2:
            speed_score = 40
        elif speed_mbps >= 1:
            speed_score = 30
        elif speed_mbps >= 0.2:
            speed_score = 20
        elif speed_mbps >= 0.05:
            speed_score = 10
        else:
            speed_score = 5  # 极低速度也给保底分，不直接0分

        return min(base_score + speed_score, 100)

# ==================== 频道名称处理器 ====================
class NameProcessor:
    _simplify_cache: Dict[str, str] = {}
    _simplify_lock  = threading.Lock()
    OVERSEAS_PREFIX = [
        'TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
        'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠', 'HOY', '澳广视', 'TDM'
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
        # 特殊处理CCTV5+
        if num == '5':
            return 'CCTV5+' if (plus or '+' in upper) else 'CCTV5'
        # 特殊处理CCTV4K
        if num == '4' and 'K' in upper:
            return 'CCTV4K'
        return f'CCTV{num}'

    @staticmethod
    def simplify(text: str) -> str:
        """繁→简转换，双层缓存提升性能"""
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
        """频道名全流程清洗：emoji→前缀提取→噪音去除→标准化→繁简转换"""
        if not name or not name.strip():
            return '未知频道'
        # 去除emoji
        n = RegexPatterns.EMOJI.sub('', name)
        # 境外频道前缀提取
        for prefix in NameProcessor.OVERSEAS_PREFIX:
            if n.upper().startswith(prefix.upper()) and len(n) > len(prefix) + 1:
                m = re.search(rf'({re.escape(prefix)}[A-Za-z0-9\u4e00-\u9fff]+)', n, re.IGNORECASE)
                if m:
                    n = m.group(1)
                    break
        # 去除噪音字符
        n = RegexPatterns.NOISE.sub('', n)
        # 非高清频道优先提取CCTV标准化名称
        if not RegexPatterns.HIRES.search(n):
            m = RegexPatterns.CCTV_FIND.search(n)
            if m:
                return NameProcessor.normalize_cctv(m.group(1).upper())
        # 去除后缀冗余
        n = RegexPatterns.SUFFIX.sub('', n)
        # 繁简转换与CCTV标准化
        n = NameProcessor.simplify(n)
        n = NameProcessor.normalize_cctv(n)
        # 空值兜底
        if not n or RegexPatterns.BLANK.match(n):
            return '未知频道'
        return n.strip()

    @staticmethod
    @lru_cache(maxsize=5000)
    def is_overseas(name: str) -> bool:
        """判断是否为境外频道，匹配超时规则"""
        return any(kw in name.upper() for kw in Config.OVERSEAS_KEYWORDS)

    @staticmethod
    @lru_cache(maxsize=8192)
    def get_category(name: str) -> Optional[str]:
        """频道分类匹配，按优先级顺序匹配"""
        s = NameProcessor.simplify(name)
        # 黑名单频道直接过滤
        if any(kw in s for kw in Config.BLACKLIST):
            return None
        # 按优先级顺序匹配分类
        for cat in Config.CATEGORY_ORDER[:-1]:
            if cat in Config.CATEGORY_RULES_COMPILED:
                if Config.CATEGORY_RULES_COMPILED[cat].search(s):
                    return cat
        # 兜底分类
        return '其他頻道'

    @staticmethod
    def normalize(name: str) -> str:
        """输出前最终标准化，增加兜底"""
        cleaned = NameProcessor.clean(name)
        # 兜底：清洗后为空，使用原名称
        return cleaned if cleaned != '未知频道' else name.strip()

# ==================== 主程序 ====================
class IPTVChecker:
    def __init__(self):
        self.logger  = logging.getLogger(__name__)
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats   = {
            'total': 0, 'valid': 0, 'failed': 0,
            'by_overseas': {'cn': 0, 'overseas': 0},
            'by_category': {cat: 0 for cat in Config.CATEGORY_ORDER},
            'filtered_by_quality': 0  # 新增：质量过滤掉的源数量
        }

    def setup_logger(self):
        """日志初始化"""
        self.logger.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def pre_check(self, input_file: Path, output_file: Path) -> bool:
        """环境预检，ffprobe依赖检查与文件备份"""
        # ffprobe依赖检查
        try:
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
            self.logger.info("✅ ffprobe 正常")
        except Exception:
            self.logger.error("❌ 未安装 ffprobe，请先安装 FFmpeg 并配置环境变量")
            return False
        # 输入文件检查
        if not input_file.exists() and Config.ENABLE_LOCAL_CHECK:
            self.logger.warning(f"⚠️ 本地输入文件不存在: {input_file}")
        # 自动备份
        if Config.AUTO_BACKUP and output_file.exists():
            ts = time.strftime('%Y%m%d_%H%M%S')
            backup_file = output_file.with_name(f"{output_file.stem}_backup_{ts}.txt")
            output_file.rename(backup_file)
            self.logger.info(f"📦 备份原文件: {backup_file.name}")
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]):
        """源数据预处理：名称清洗→有效性校验→指纹去重→域名分组，新增点播域名过滤"""
        for line in lines:
            if ',' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            url  = url_part.strip()
            name = NameProcessor.clean(name_part.strip())
            # 过滤无效名称与URL
            if not name or name == '未知频道':
                continue
            if not URLCleaner.is_valid(url):
                continue
            if not URLCleaner.filter_private_ip(url):
                continue
            
            # ✅ 新增：点播域名过滤（只保留符合直播关键词的名称）
            parsed = urlparse(url)
            domain = parsed.netloc.split(':')[0].lower()
            if URLCleaner.is_vod_domain(url):
                # 域名命中点播列表，检查名称是否为直播频道
                if not Config.LIVE_CHANNEL_KEYWORDS.search(name):
                    # 名称无直播关键词，跳过（可能是短视频/音频点播）
                    continue
            
            # 指纹去重
            fp = URLCleaner.get_fingerprint(url)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            # 域名分组
            domain_lines[domain].append(f"{name},{url}")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        """同步运行主流程"""
        seen_fp      = pre_seen_fp      if pre_seen_fp      is not None else set()
        domain_lines = pre_domain_lines if pre_domain_lines is not None else defaultdict(list)
        lines_to_check: List[str] = []

        # 1. 读取本地文件（仅当 ENABLE_LOCAL_CHECK=True 或显式指定输入文件）
        input_path = args.input if args.input else Config.INPUT_FILE
        if Config.ENABLE_LOCAL_CHECK and input_path:
            self.logger.info(f"📂 读取本地文件：{input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    local_lines = [l.strip() for l in f if l.strip()]
                self.process_lines(local_lines, seen_fp, domain_lines)
                self.logger.info(f"✅ 本地文件处理完成：{len(local_lines)}条")
            except Exception as e:
                self.logger.error(f"❌ 读取本地文件失败: {e}")

        # 2. 拉取预设网络源
        successful_web_sources: List[str] = []
        if Config.ENABLE_WEB_CHECK and not args.no_web:
            web_sources = Config.PRESET_FILES
            self.logger.info(f"🌐 并发拉取 {len(web_sources)} 个预设网络源...")
            with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                future_to_url = {executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                                 for url in web_sources}
                success_count = fail_count = total_extracted = 0
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

        # 3. 收集待测源，按域名限制数量
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

        # 统计境内外数量
        overseas_total = sum(1 for ln in lines_to_check if NameProcessor.is_overseas(ln.split(',', 1)[0]))
        self.logger.info(f"📋 待测源统计: 总计 {total} 条 | 境内 {total - overseas_total} 条 | 境外 {overseas_total} 条")

        # 初始化分类容器
        cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list: List[str] = []
        real_workers = min(args.workers, total)
        self.logger.info(f"🚀 启动并发检测：{real_workers}个工作线程")

        # 4. 并发测活
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="测活中", unit="源", ncols=80) as pbar:
            futures = [executor.submit(self.checker.check, ln, Config.PROXY) for ln in lines_to_check]
            for future in as_completed(futures):
                r = future.result()
                pbar.update(1)
                if r["status"] == "有效":
                    self.stats['valid'] += 1
                    self.stats['by_overseas']['overseas' if r["overseas"] else 'cn'] += 1
                    cat = NameProcessor.get_category(r["name"])
                    if cat and cat in cat_map:
                        cat_map[cat].append(r)
                        self.stats['by_category'][cat] += 1
                else:
                    self.stats['failed'] += 1
                    if Config.ARCHIVE_FAIL:
                        fail_list.append(f"{r['name']},{r['url']}")
                # 更新进度条有效率
                pbar.set_postfix({"有效率": f"{self.stats['valid'] / pbar.n * 100:.1f}%"})

        # 5. 失效源归档
        if Config.ARCHIVE_FAIL and fail_list:
            self.write_failures(fail_list)

        # 6. 写入结果文件
        output_file = args.output if args.output else str(Config.OUTPUT_FILE)
        self.write_results(output_file, cat_map, total)

    async def run_async(self, args):
        """异步运行模式（启用异步爬虫）"""
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)

        # 异步爬虫爬取新源
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            self.logger.info("🌐 启动异步爬虫，扫描新增网络源...")
            async with AsyncWebSourceCrawler() as crawler:
                url_to_name = await crawler.crawl_all_with_names()
                if url_to_name:
                    self.logger.info(f"🔍 发现新增源: {len(url_to_name)} 个")
                    for url, name in url_to_name.items():
                        # 有效性检查
                        if not URLCleaner.is_valid(url):
                            continue
                        if not URLCleaner.filter_private_ip(url):
                            continue
                        # 黑名单关键词过滤
                        if any(kw in name for kw in Config.BLACKLIST):
                            continue
                        # 点播域名过滤（无直播关键词则跳过）
                        if URLCleaner.is_vod_domain(url):
                            if not Config.LIVE_CHANNEL_KEYWORDS.search(name):
                                continue
                        # 频道名清洗
                        name = NameProcessor.clean(name)
                        if not name or name == '未知频道':
                            continue
                        # 指纹去重并加入待测列表
                        fp = URLCleaner.get_fingerprint(url)
                        if fp not in seen_fp:
                            seen_fp.add(fp)
                            domain_lines["crawled_sources"].append(f"{name},{url}")
                    self.logger.info(f"✅ 新增源已加入待测列表: {len(domain_lines['crawled_sources'])} 个")

        # 调用同步主流程完成后续处理
        self.run(args, pre_seen_fp=seen_fp, pre_domain_lines=domain_lines)

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int):
        """修复：空分类不写入，质量过滤增加兜底，确保有效源写入"""
        output_path = Path(output_file)
        tmp_path    = output_path.with_suffix('.tmp')
        total_written = 0  # 统计实际写入的源数量

        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for cat in Config.CATEGORY_ORDER:
                    channels = cat_map.get(cat, [])
                    if not channels:
                        continue

                    # 按质量评分降序排序
                    channels.sort(key=lambda x: x.get('quality', 0), reverse=True)

                    # 按频道名分组，限制单频道最大链接数
                    grouped: Dict[str, List[Dict]] = defaultdict(list)
                    for ch in channels:
                        # 质量过滤 + 兜底逻辑：每个频道至少保留1条最高质量的源
                        name = NameProcessor.normalize(ch['name'])
                        # 先加入分组
                        if len(grouped[name]) < Config.MAX_LINKS_PER_NAME:
                            grouped[name].append(ch)

                    # 质量过滤处理
                    final_grouped: Dict[str, List[Dict]] = defaultdict(list)
                    for name, items in grouped.items():
                        # 过滤掉质量不达标的源
                        filtered = []
                        for ch in items:
                            if not Config.ENABLE_QUALITY_FILTER or ch.get('quality', 0) >= Config.MIN_QUALITY_SCORE:
                                filtered.append(ch)
                            else:
                                self.stats['filtered_by_quality'] += 1
                        # 兜底：如果过滤后为空，保留质量最高的1条
                        if not filtered and items:
                            filtered = [max(items, key=lambda x: x.get('quality', 0))]
                        final_grouped[name] = filtered

                    # 修复：没有可写入内容的分类，跳过不写分类头
                    total_channels_in_cat = sum(len(items) for items in final_grouped.values())
                    if total_channels_in_cat <= 0:
                        continue

                    # 写入分类头与内容
                    f.write(f"{cat},#genre#\n")
                    total_written += total_channels_in_cat

                    # 央卫频道特殊排序
                    if cat == "央衛頻道":
                        # 1. CCTV1-17 按数字顺序
                        cctv_ch:  Dict[str, List[Dict]] = {}
                        central_ch: Dict[str, List[Dict]] = {}
                        other_ch: Dict[str, List[Dict]] = {}
                        for name, items in final_grouped.items():
                            if name.startswith('CCTV'):
                                cctv_ch[name] = items
                            elif '中央' in name or '央视' in name:
                                central_ch[name] = items
                            else:
                                other_ch[name] = items
                        # 写入CCTV1-17
                        for num in range(1, 18):
                            key = f"CCTV{num}"
                            if key in cctv_ch:
                                for ch in sorted(cctv_ch[key], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                    f.write(f"{ch['name']},{ch['url']}\n")
                        # 写入CCTV5+
                        if 'CCTV5+' in cctv_ch:
                            for ch in sorted(cctv_ch['CCTV5+'], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{ch['name']},{ch['url']}\n")
                        # 写入中央/央视频道
                        for name in sorted(central_ch.keys(),
                                           key=lambda n: max(c.get('quality', 0) for c in central_ch[n]),
                                           reverse=True):
                            for ch in sorted(central_ch[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{ch['name']},{ch['url']}\n")
                        # 写入其他央卫频道
                        for name in sorted(other_ch.keys(),
                                           key=lambda n: max(c.get('quality', 0) for c in other_ch[n]),
                                           reverse=True):
                            for ch in sorted(other_ch[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{ch['name']},{ch['url']}\n")
                    else:
                        # 其他分类按质量降序写入
                        for name in sorted(final_grouped.keys(),
                                           key=lambda n: max(c.get('quality', 0) for c in final_grouped[n]),
                                           reverse=True):
                            for ch in sorted(final_grouped[name], key=lambda x: -x.get('quality', 0))[:Config.MAX_LINKS_PER_NAME]:
                                f.write(f"{ch['name']},{ch['url']}\n")
                    f.write("\n")
            # 原子替换，避免文件损坏
            tmp_path.replace(output_path)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise e

        # 输出最终统计（修复数据对齐问题）
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: 总计 {total} 条")
        self.logger.info(f"✅ 测活有效: {self.stats['valid']} 条 | 失效: {self.stats['failed']} 条")
        self.logger.info(f"⚠️  质量过滤: {self.stats['filtered_by_quality']} 条 | 最终写入: {total_written} 条")
        self.logger.info(f"✅ 整体有效率: {self.stats['valid']/total*100:.1f}%")
        self.logger.info(f"📊 境内有效: {self.stats['by_overseas']['cn']} 条 | 境外有效: {self.stats['by_overseas']['overseas']} 条")
        self.logger.info(f"📋 分类有效统计:")
        for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: -x[1]):
            if count > 0:
                self.logger.info(f"   {cat}: {count} 条")
        self.logger.info(f"📁 结果文件: {output_path.absolute()}")
        self.logger.info(f"{'='*60}\n")

    def write_failures(self, fail_list: List[str]):
        """原子写入失效源归档"""
        fail_path = Config.BASE_DIR / "live_fail.txt"
        tmp_path  = fail_path.with_suffix('.tmp')
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(fail_list))
            tmp_path.replace(fail_path)
            self.logger.info(f"📁 失效源归档完成: {fail_path.absolute()} ({len(fail_list)}条)")
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            self.logger.warning(f"⚠️ 写入失效源失败: {e}")

# ==================== 命令行入口 ====================
def main():
    # 加载配置
    Config.load_from_file()
    # 命令行参数解析
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 修复版')
    parser.add_argument('-i', '--input',   default=None,  help='输入文件路径')
    parser.add_argument('-o', '--output',  default=None,  help='输出文件路径')
    parser.add_argument('-w', '--workers', type=int, default=Config.MAX_WORKERS, help='并发检测线程数')
    parser.add_argument('-t', '--timeout', type=int, default=Config.TIMEOUT_CN, help='境内源超时时间(秒)')
    parser.add_argument('--no-web',        action='store_true',  help='跳过预设网络源拉取')
    parser.add_argument('--proxy',         default=None,  help='代理地址 (如 http://127.0.0.1:7890)')
    parser.add_argument('--async-crawl',   action='store_true',  help='启用异步爬虫扫描新源')
    parser.add_argument('--no-speed-check',action='store_true',  help='关闭下载速度检测')
    args = parser.parse_args()

    # 参数覆盖配置
    if args.timeout:
        Config.TIMEOUT_CN       = args.timeout
        Config.TIMEOUT_OVERSEAS = args.timeout * 2
    if args.workers:
        Config.MAX_WORKERS = args.workers
    if args.proxy:
        Config.PROXY = args.proxy
    if args.no_speed_check:
        Config.ENABLE_SPEED_CHECK = False

    # 路径初始化
    input_file  = Path(args.input)  if args.input  else Config.INPUT_FILE
    output_file = Path(args.output) if args.output else Config.OUTPUT_FILE

    # 初始化检查器
    checker = IPTVChecker()
    checker.setup_logger()

    # 环境预检
    print(f"{'='*60}")
    print("🔍 开始环境预检...")
    if not checker.pre_check(input_file, output_file):
        sys.exit(1)
    print(f"{'='*60}\n")

    # ==================== 🔥 修复：自动按配置开关执行爬取 ====================
    try:
        # 只要 ENABLE_WEB_FETCH = True，自动启动异步爬取，无需手动加参数
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            asyncio.run(checker.run_async(args))
        else:
            checker.run(args)
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动中断程序")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序运行异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()