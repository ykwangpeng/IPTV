import sys, re, time, json, random, argparse, warnings, subprocess, asyncio, logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from functools import lru_cache, wraps
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, urlencode
import threading
import multiprocessing
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

# 初始化日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iptv_apex.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== 配置管理 ====================
class Config:
    BASE_DIR = Path(__file__).parent
    INPUT_FILE  = BASE_DIR / "paste.txt"
    OUTPUT_FILE = BASE_DIR / "live_ok.txt"
    CONFIG_FILE = BASE_DIR / "config.json"

    # 核心功能开关
    ENABLE_WEB_FETCH    = False  # 是否启用自动爬取新增网络直播源的功能
    ENABLE_WEB_CHECK    = False  # 是否启用拉取并检测预设网络源的功能
    ENABLE_LOCAL_CHECK  = True   # 是否启用读取并检测本地输入文件的功能
    ENABLE_SPEED_CHECK  = True   # 是否启用下载速度检测
    DEBUG_MODE          = False  # 调试模式开关
    AUTO_BACKUP         = True   # 自动备份开关（备份文件名含时间戳）
    ARCHIVE_FAIL        = True   # 失效源归档开关

    # 性能与超时配置（动态并发+合理超时）
    MAX_WORKERS         = min(80, multiprocessing.cpu_count() * 10)  # 基于CPU核心数动态调整
    FETCH_WORKERS       = 4      # 网络源拉取的最大并发线程数
    TIMEOUT_CN          = 8      # 境内直播源检测超时时间（秒）- 优化自Lity版本
    TIMEOUT_OVERSEAS    = 15     # 境外直播源检测超时时间（秒）- 优化自Lity版本
    RETRY_COUNT         = 2      # 网络请求重试次数
    REQUEST_JITTER      = False  # 请求抖动开关
    MAX_LINKS_PER_NAME  = 3      # 每个频道保留的最大有效链接数
    MAX_SOURCES_PER_DOMAIN = 0   # 每个域名最多保留的源数量（0=不限制）

    # 过滤与质量配置
    FILTER_PRIVATE_IP       = True   # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False  # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER   = True   # 质量过滤开关
    MIN_QUALITY_SCORE       = 80     # 最低质量评分阈值（≤3s延迟=80分，刚好合格）
    MIN_SPEED_MBPS          = 0.005  # 最低下载速度阈值（MB/s），低于此值直接判定失效
    SPEED_CHECK_BYTES       = 32768  # 速度检测下载字节数（32KB）- 优化自Lity版本

    # IPv6 优化配置（真实测活+延迟加权，修复db版本的不合理逻辑）
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

    # 频道黑名单（补充db版本的完整关键词）
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

    # 直播源致命错误关键词（精准匹配，移除模糊关键词避免误判）
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
        "405 method not allowed"
    }

    # 频道分类规则（整合所有版本优势，精简冗余，补充关键词）
    CATEGORY_RULES_COMPILED: Dict = {}
    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR", "杜比视界"],
        "央衛頻道": ["CCTV", "中央", "央视", "卫视", "CETV", "中国教育", "兵团", "农林"],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "咪咕", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J联赛", "K联赛", "美职",
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
            "爱奇艺", "优酷", "腾讯视频", "芒果TV", "IQIYI", "POPC",
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
            "翡翠", "博斯", "凤凰", "TVB", "香港", "华文", "八度", "华艺", "环球",
            "生命", "镜", "澳", "台湾", "探索", "年代", "明珠", "唯心", "公视",
            "东森", "三立", "爱尔达", "NOW", "VIU", "STAR", "星空", "纬来",
            "非凡", "中天", "中视", "无线", "寰宇", "Z频道", "GOOD", "ROCK",
            "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天", "AXN",
            "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "奇妙电视", "香港开电视", "有线宽频", "ViuTVsix", "ViuTVtwo", "澳广视",
            "TDM", "澳门卫视", "壹电视", "CTI", "CTS", "PTS", "RHK", "TTV",
            "FTV", "中天亚洲", "东森亚洲", "年代新闻", "东森新闻", "中天新闻",
            "民视新闻", "台视新闻", "华视新闻", "三立新闻", "非凡新闻", "TVBS新闻",
            "凤凰卫视资讯台", "凤凰卫视中文台", "凤凰卫视香港台"
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

    # 点播域名黑名单（短视频/点播平台域名，非直播源）
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

    # 直播频道名关键词（用于识别真正的直播频道，区分点播内容）
    LIVE_CHANNEL_KEYWORDS = re.compile(
        r'频道|台|卫视|影院|剧场|电影|剧集|直播|体育|音乐|新闻|综合|少儿|动漫|教育|财经|'
        r'Discovery|Channel|TV|News|Live|Sport|Music|Kids|Movie|Film|Drama|Anime'
    )

    @classmethod
    def validate_config(cls):
        """校验配置合法性，避免非法值导致运行异常"""
        cls.MAX_WORKERS = max(1, cls.MAX_WORKERS)
        cls.FETCH_WORKERS = max(1, cls.FETCH_WORKERS)
        cls.TIMEOUT_CN = max(1, cls.TIMEOUT_CN)
        cls.TIMEOUT_OVERSEAS = max(1, cls.TIMEOUT_OVERSEAS)
        cls.RETRY_COUNT = max(0, cls.RETRY_COUNT)
        cls.MAX_LINKS_PER_NAME = max(1, cls.MAX_LINKS_PER_NAME)
        cls.MIN_QUALITY_SCORE = max(0, cls.MIN_QUALITY_SCORE)
        cls.MIN_SPEED_MBPS = max(0, cls.MIN_SPEED_MBPS)
        cls.SPEED_CHECK_BYTES = max(1024, cls.SPEED_CHECK_BYTES)
        cls.IPV6_LATENCY_BONUS = max(0, cls.IPV6_LATENCY_BONUS)
        logger.info("✅ 配置校验完成，非法值已自动修正")

    @classmethod
    def init_compiled_rules(cls):
        """初始化时预编译分类正则表达式，提升匹配效率"""
        for cat, keywords in cls.CATEGORY_RULES.items():
            pattern = '|'.join(re.escape(kw) for kw in keywords)
            cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)
        logger.info("✅ 分类规则正则预编译完成")

    @classmethod
    def load_from_file(cls):
        """白名单机制加载配置，缺失字段保留默认值"""
        if not cls.CONFIG_FILE.exists():
            logger.info("ℹ️ 配置文件不存在，使用默认配置")
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
                loaded_str = ' | '.join(
                    f"{k}={getattr(cls, k)}" for k in sorted(loaded)
                    if not isinstance(getattr(cls, k), (list, dict))
                )
                logger.info(f"✅ 加载配置文件成功（{len(loaded)}项）：{loaded_str}")
            else:
                logger.info("✅ 配置文件无有效字段，使用默认配置")
        except Exception as e:
            logger.warning(f"⚠️ 加载配置文件失败：{e}，使用默认配置")

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
            logger.info(f"✅ 保存网页源到配置文件：{cls.CONFIG_FILE}")
        except Exception as e:
            logger.warning(f"⚠️ 保存配置文件失败：{e}")

# 初始化配置
Config.validate_config()
Config.init_compiled_rules()
Config.load_from_file()

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

# ==================== 工具函数 ====================
def is_vod_domain(url: str) -> bool:
    """检测URL是否为点播域名，非直播源"""
    try:
        domain = urlparse(url).netloc.split(':')[0]
        return domain in Config.VOD_DOMAINS
    except Exception as e:
        logger.debug(f"检测点播域名失败：{url} - {e}")
        return False

# ==================== 重试装饰器（优化：非致命错误跳过重试） ====================
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
                    # 非致命错误（如404）直接终止重试，减少无效请求
                    if any(kw in str(e).lower() for kw in ["404", "403", "invalid url"]):
                        break
                    if attempt < attempts - 1:
                        sleep_time = delay * (backoff ** attempt)
                        logger.debug(f"🔄 重试 {func.__name__} (第{attempt+1}次)，延迟 {sleep_time:.2f}s：{e}")
                        time.sleep(sleep_time)
            if last_exception:
                logger.error(f"❌ {func.__name__} 重试{attempts}次失败：{last_exception}")
                raise last_exception
            return None
        return wrapper
    return decorator

# ==================== 同步下载速度检测（解决多线程事件循环冲突） ====================
@retry()
def check_download_speed(url: str, timeout: int = None) -> Tuple[float, float]:
    """
    检测下载速度
    返回：(延迟秒数, 速度MB/s)
    """
    if not Config.ENABLE_SPEED_CHECK:
        return (0.0, 10.0)  # 禁用测速时返回默认值
    
    timeout = timeout or (Config.TIMEOUT_CN if not any(kw in url for kw in Config.OVERSEAS_KEYWORDS) else Config.TIMEOUT_OVERSEAS)
    headers = {'User-Agent': random.choice(Config.UA_POOL)}
    
    try:
        # 检测是否为点播源
        if is_vod_domain(url):
            logger.debug(f"跳过点播源测速：{url}")
            return (999.0, 0.0)
        
        # 发起请求（仅下载指定字节数）
        start_time = time.time()
        with requests.get(
            url, 
            headers=headers, 
            timeout=timeout, 
            stream=True, 
            proxies=Config.PROXY,
            verify=False
        ) as resp:
            if resp.status_code != 200:
                raise Exception(f"HTTP状态码异常：{resp.status_code}")
            
            # 计算延迟
            latency = time.time() - start_time
            
            # 下载指定字节数并计算速度
            total_bytes = 0
            chunk_size = 4096
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes >= Config.SPEED_CHECK_BYTES:
                    break
            
            # 计算速度（MB/s）
            download_time = time.time() - start_time
            speed_mbps = (total_bytes / (1024 * 1024)) / max(download_time, 0.001)
            
            # IPv6延迟加权
            if Config.ENABLE_IPV6_OPTIMIZE and ':' in urlparse(url).netloc:
                latency -= Config.IPV6_LATENCY_BONUS / 1000  # 转换为秒
                latency = max(0.0, latency)  # 避免延迟为负
            
            logger.debug(f"📶 测速 {url}：延迟 {latency:.3f}s，速度 {speed_mbps:.3f}MB/s")
            return (latency, speed_mbps)
    
    except Exception as e:
        logger.debug(f"测速失败 {url}：{e}")
        return (999.0, 0.0)

# ==================== 核心业务逻辑（示例：频道名清洗） ====================
def clean_channel_name(name: str) -> str:
    """
    清洗频道名：移除表情、冗余字符、标准化格式
    """
    if not name:
        return ""
    
    # 转简体 + 去除首尾空格
    name = zhconv.convert(name.strip(), 'zh-cn')
    
    # 移除表情
    name = RegexPatterns.EMOJI.sub('', name)
    
    # 移除噪声字符（括号、标签等）
    name = RegexPatterns.NOISE.sub('', name)
    
    # 移除空白字符
    name = RegexPatterns.BLANK.sub('', name)
    
    # 标准化CCTV命名
    cctv_match = RegexPatterns.CCTV_FIND.search(name)
    if cctv_match:
        cctv_str = cctv_match.group(1)
        standard_cctv = RegexPatterns.CCTV_STANDARD.sub(r'CCTV\1\2', cctv_str)
        name = name.replace(cctv_str, standard_cctv)
    
    # 移除后缀（高清、线路等）
    name = RegexPatterns.SUFFIX.split(name)[0]
    
    return name.strip()

# ==================== 主函数（示例） ====================
def main():
    logger.info("🚀 启动IPTV-Apex直播源处理工具")
    
    # 示例：读取本地文件
    if Config.ENABLE_LOCAL_CHECK and Config.INPUT_FILE.exists():
        with open(Config.INPUT_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 处理进度条
        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            futures = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                futures.append(executor.submit(process_single_source, line))
            
            # 处理结果
            results = []
            for future in tqdm(as_completed(futures), total=len(futures), desc="处理直播源"):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"处理直播源失败：{e}")
            
            # 保存有效源
            if results:
                with open(Config.OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(results))
                logger.info(f"✅ 处理完成，有效源数量：{len(results)}，已保存至 {Config.OUTPUT_FILE}")
            else:
                logger.warning("⚠️ 未找到有效直播源")
    
    logger.info("🏁 IPTV-Apex处理完成")

def process_single_source(line: str) -> Optional[str]:
    """处理单个直播源：清洗、测活、测速、分类"""
    try:
        # 分割频道名和URL（适配m3u格式和纯文本格式）
        if ',' in line:
            name, url = line.split(',', 1)
        else:
            name = url = line
        
        # 1. 清洗频道名
        clean_name = clean_channel_name(name)
        if not clean_name or any(kw in clean_name for kw in Config.BLACKLIST):
            logger.debug(f"过滤黑名单频道：{clean_name}")
            return None
        
        # 2. 过滤内网IP和点播源
        if RegexPatterns.PRIVATE_IP.match(url) or is_vod_domain(url):
            logger.debug(f"过滤内网/点播源：{clean_name} - {url}")
            return None
        
        # 3. 测活+测速
        latency, speed = check_download_speed(url)
        if speed < Config.MIN_SPEED_MBPS:
            logger.debug(f"速度过低过滤：{clean_name} - {url} (速度：{speed:.3f}MB/s)")
            return None
        
        # 4. 质量评分（延迟越低评分越高）
        quality_score = 100 - min(latency * 10, 99)  # 延迟3s=70分，延迟10s=10分
        if Config.ENABLE_IPV6_OPTIMIZE and ':' in urlparse(url).netloc:
            quality_score += Config.IPV6_LATENCY_BONUS
        quality_score = max(0, min(100, quality_score))
        
        if Config.ENABLE_QUALITY_FILTER and quality_score < Config.MIN_QUALITY_SCORE:
            logger.debug(f"质量评分过低过滤：{clean_name} - {url} (评分：{quality_score:.1f})")
            return None
        
        # 5. 分类匹配
        category = "其他頻道"
        for cat in Config.CATEGORY_ORDER:
            if cat == "其他頻道":
                continue
            if Config.CATEGORY_RULES_COMPILED[cat].search(clean_name):
                category = cat
                break
        
        # 6. 构造输出格式（M3U格式）
        output = f"#EXTINF:-1 group-title=\"{category}\",{clean_name}\n{url}"
        logger.debug(f"✅ 有效源：{category} - {clean_name} (延迟：{latency:.3f}s，速度：{speed:.3f}MB/s，评分：{quality_score:.1f})")
        return output
    
    except Exception as e:
        logger.error(f"处理直播源失败：{line} - {e}")
        return None

if __name__ == "__main__":
    main()