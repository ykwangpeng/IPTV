import warnings
warnings.filterwarnings('ignore')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import time
import os
import re
import random
import multiprocessing
import argparse
from urllib.parse import urlparse, parse_qs, urlencode
from tqdm import tqdm
import requests
import logging
from collections import defaultdict
# 强制导入zhconv库进行繁简转换
import zhconv
# ─────────────────────────────────────────────
#  默认配置（可通过命令行参数覆盖）
# ─────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE        = os.path.join(BASE_DIR, "paste.txt")
OUTPUT_FILE       = os.path.join(BASE_DIR, "live_ok.txt")
FAIL_FILE         = os.path.join(BASE_DIR, "live_fail.txt")
LOG_FILE          = os.path.join(BASE_DIR, "iptv_check.log")
DEBUG_MODE            = False
AUTO_BACKUP           = True
ARCHIVE_FAIL          = True
MAX_WORKERS           = 60
FETCH_WORKERS         = 8      
TIMEOUT_CN            = 15
TIMEOUT_OVERSEAS      = 30
RETRY_COUNT           = 3
REQUEST_JITTER        = True
MAX_LINKS_PER_NAME    = 3
FILTER_PRIVATE_IP     = True
REMOVE_REDUNDANT_PARAMS = False
WEB_SOURCES = [
    "https://raw.githubusercontent.com/gb1984/iptv/main/iptv.m3u",
    "https://raw.githubusercontent.com/dongyubin/IPTV/main/iptv.m3u",
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
    "https://live.hacks.tools/tv/ipv4/categories/电影频道.m3u",
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
REFERER = 'https://www.baidu.com'
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
# 分类关键词配置（外置为字典，便于独立维护）
CATEGORY_RULES = {
    "4K專區":    ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"],
    "央視頻道":   ["CCTV", "中央", "央视"],
    "各地衛視":   ["卫视"],
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
# 输出分类顺序
CATEGORY_ORDER = ["4K專區", "央視頻道", "各地衛視", "體育賽事", "少兒動漫", "音樂頻道", "影視劇集", "港澳台頻", "其他頻道"]
PROXY = None  # 示例: 'http://127.0.0.1:7897'
# ─────────────────────────────────────────────
#  预编译正则（避免重复编译）
# ─────────────────────────────────────────────
_PRIVATE_IP_RE = re.compile(
    r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|'
    r'::1$|fc00:|fe80:|fd[0-9a-f]{2}:|localhost|0\.0\.0\.0)',
    re.IGNORECASE
)
# 匹配所有emoji、特殊符号（含心形❤️、星星✨、火焰🔥等）
_EMOJI_RE      = re.compile(r'[\U00010000-\U0010ffff\U00002600-\U000027ff\U0000f600-\U0000f6ff\U0000f300-\U0000f3ff\U00002300-\U000023ff\U00002500-\U000025ff\U00002100-\U000021ff\U000000a9\U000000ae\U00002000-\U0000206f\U00002460-\U000024ff\U00001f00-\U00001fff]+', re.UNICODE)
_CCTV_NORM_RE  = re.compile(r'(?i)(CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*(\d{1,2})(\+)?')
_CCTV_FIND_RE  = re.compile(r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)')
_HIRES_RE      = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清')  
_NOISE_RE      = re.compile(r'\(.*?\)|\)|\[.*?\]|【.*?】|《.*?》|<.*?>|\{.*?\}')
_SUFFIX_RE     = re.compile(r'(?i)[-_—～•·:\s|/\\]|HD|1080p|720p|360p|4Gtv|540p|高清|超清|超高清|标清|直播|主线|台$')
_BLANK_RE      = re.compile(r'^[\s\-—_～•·:·]+$')
# CCTV命名标准化：仅CCTV5+保留+号，其余去+号+数字去前置0
# 【终极严格版】CCTV命名标准化：仅允许 CCTV5 和 CCTV5+，其余全部纯数字、无+号
def normalize_cctv(name: str) -> str:
    if not name:
        return name
    # 统一转为大写，兼容全角ＣＣＴＶ、半角CCTV
    upper_name = name.upper().replace("ＣＣＴＶ", "CCTV")
    if not upper_name.startswith('CCTV'):
        return name

    # 精准匹配：CCTV + 任意分隔符 + 数字 + 可选+号（覆盖所有乱格式）
    cctv_pattern = re.compile(r'CCTV\D*?(\d{1,2})\s*\+?', re.IGNORECASE)
    match = cctv_pattern.search(upper_name)
    if not match:
        return name

    # 提取数字并去掉前置0（02→2，05→5）
    num = str(int(match.group(1)))
    
    # 【核心规则】只有数字5允许带+，其他一律纯数字
    if num == "5":
        # 检查原始名称是否包含+号，包含则为 CCTV5+，否则为 CCTV5
        if "+" in upper_name:
            return "CCTV5+"
        else:
            return "CCTV5"
    else:
        # 其他频道：纯格式，绝对无+号
        return f"CCTV{num}"
_TVG_NAME_RE   = re.compile(r'tvg-name="([^"]+)"')
_DATE_TAG_RE   = re.compile(r'更新日期:.*')
# ─────────────────────────────────────────────
#  命令行参数解析
# ─────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 (优化版)')
    parser.add_argument('--input',    type=str,   default=None,         help='本地输入文件路径')
    parser.add_argument('--output',   type=str,   default=None,         help='输出文件路径')
    parser.add_argument('--workers',  type=int,   default=MAX_WORKERS,  help=f'并发检测线程数 (默认 {MAX_WORKERS})')
    parser.add_argument('--proxy',    type=str,   default=PROXY,        help='HTTP/HTTPS 代理地址')
    parser.add_argument('--timeout',  type=int,   default=None,         help='境内超时秒数 (默认 20)')
    parser.add_argument('--debug',    action='store_true',              help='开启调试输出')
    parser.add_argument('--no-web',   action='store_true',              help='跳过网络源拉取，仅检测本地文件')
    return parser.parse_args()
# ─────────────────────────────────────────────
#  日志初始化
# ─────────────────────────────────────────────
def init_logger(debug: bool = False) -> logging.Logger:
    logger = logging.getLogger("IPTV_CHECK")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='w')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    fh.setLevel(logging.DEBUG if debug else logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(message)s'))
    ch.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
logger = init_logger()
# ─────────────────────────────────────────────
#  繁简转换：强制使用zhconv库，转换为简体中文
# ─────────────────────────────────────────────
def simplify(text: str) -> str:
    if not text or not isinstance(text, str):
        return text or ""
    # 转换为简体中文，strip去除首尾空格
    return zhconv.convert(text, 'zh-hans').strip()
# ─────────────────────────────────────────────
#  频道名清洗
# ─────────────────────────────────────────────
_OVERSEAS_PREFIX = ['TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
                    'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠']
def clean_name(n: str) -> str:
    if not n or n.strip() == "":
        return "未知频道"
    n = _EMOJI_RE.sub('', n)
    # 境外前缀提取
    for prefix in _OVERSEAS_PREFIX:
        if n.startswith(prefix) and len(n) > len(prefix) + 1:
            m = re.search(rf'({re.escape(prefix)}[A-Za-z0-9\u4e00-\u9fff\u3400-\u4dbf\u8000-\u9fff]+)', n)
            if m:
                n = m.group(1)
                break
    n = _NOISE_RE.sub('', n)
    n = _CCTV_NORM_RE.sub(r'CCTV\2\3', n)
    # 新增：第一次CCTV标准化（处理正则替换后的非规范名）
    n = normalize_cctv(n)
    if not _HIRES_RE.search(n):
        m = _CCTV_FIND_RE.search(n)
        if m:
            # 新增：匹配后标准化再返回，杜绝非规范名
            cctv_name = normalize_cctv(m.group(1).upper())
            return cctv_name
    n = _SUFFIX_RE.sub('', n)
    n = simplify(n)
    # 新增：最终标准化，防止所有遗漏情况
    n = normalize_cctv(n)
    if not n or _BLANK_RE.match(n):
        return "未知频道"
    return n.strip()
# ─────────────────────────────────────────────
#  分类判断（使用配置字典）
# ─────────────────────────────────────────────
def get_category(name: str) -> str | None:
    s = simplify(name)
    if any(k in s for k in BLACKLIST):
        return None
    # 按 CATEGORY_ORDER 优先级依次匹配（"各地衛視" 单独处理"卫视"子串）
    for cat in CATEGORY_ORDER[:-1]:  # 排除"其他頻道"
        keywords = CATEGORY_RULES.get(cat, [])
        if cat == "各地衛視":
            if "卫视" in s:
                return cat
        elif any(k in s for k in keywords):
            return cat
    return "其他頻道"
def is_overseas(name: str) -> bool:
    s = simplify(name).upper()
    return any(kw.upper() in s for kw in OVERSEAS_KEYWORDS)
# ─────────────────────────────────────────────
#  私有 IP 判断（预编译正则）
# ─────────────────────────────────────────────
def is_private_ip(host: str) -> bool:
    if not host:
        return True
    return bool(_PRIVATE_IP_RE.match(host))
# ─────────────────────────────────────────────
#  URL 指纹（去重用）
# ─────────────────────────────────────────────
def clean_url_params(url: str) -> str:
    if not REMOVE_REDUNDANT_PARAMS:
        return url
    try:
        parsed = urlparse(url)
        keep = ['codec', 'resolution', 'bitrate', 'stream', 'channel', 'id', 'pid', 'u', 'token', 'key']
        qd = parse_qs(parsed.query, keep_blank_values=True)
        fq = {k: v for k, v in qd.items() if any(kw in k.lower() for kw in keep)}
        return parsed._replace(query=urlencode(fq, doseq=True)).geturl()
    except Exception:
        return url
def get_url_fingerprint(url: str) -> str:
    try:
        cleaned = clean_url_params(url)
        p = urlparse(cleaned)
        host  = p.hostname or ""
        port  = f":{p.port}" if p.port else ""
        return f"{host}{port}{p.path}{p.query or ''}".lower()
    except Exception:
        return url.lower()
# ─────────────────────────────────────────────
#  环境预检
# ─────────────────────────────────────────────
def pre_check_env(input_file: str, output_file: str) -> bool:
    logger.info("🔍 开始环境预检...")
    try:
        proc = subprocess.run(['ffprobe', '-version'], capture_output=True, timeout=10, shell=False)
        if proc.returncode != 0:
            logger.error("❌ 未找到 ffprobe，请安装 ffmpeg 并配置到系统 PATH")
            return False
        logger.info("✅ ffprobe 环境正常")
    except FileNotFoundError:
        logger.error("❌ 未找到 ffprobe，请安装 ffmpeg 并配置到系统 PATH")
        return False
    except Exception as e:
        logger.error(f"❌ ffprobe 检查异常：{e}")
        return False
    if os.path.exists(input_file):
        logger.info(f"✅ 本地输入文件正常: {input_file}")
    else:
        logger.warning(f"⚠️  本地输入文件不存在: {input_file}，将仅使用网络源")
    if AUTO_BACKUP and os.path.exists(output_file):
        backup = output_file.replace('.txt', f'_backup_{time.strftime("%Y%m%d_%H%M%S")}.txt')
        try:
            os.rename(output_file, backup)
            logger.info(f"✅ 上次结果已备份: {backup}")
        except Exception as e:
            logger.warning(f"⚠️  备份失败: {e}")
    logger.info("✅ 环境预检通过，开始执行\n")
    return True
# ─────────────────────────────────────────────
#  M3U 解析（支持 tvg-name 属性）
# ─────────────────────────────────────────────
def parse_m3u(lines: list[str]) -> list[str]:
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
            # 优先使用 tvg-name 属性，回退到逗号后内容
            m = _TVG_NAME_RE.search(extinf_line)
            if m:
                name_part = m.group(1).strip()
            elif ',' in extinf_line:
                name_part = extinf_line.rsplit(',', 1)[-1].strip()
            else:
                name_part = '未知频道'
            name_part = _DATE_TAG_RE.sub('', name_part).strip() or '未知频道'
            parsed.append(f"{name_part},{line}")
            extinf_line = None
    logger.debug(f"parse_m3u 解析 {len(parsed)} 条")
    return parsed
# ─────────────────────────────────────────────
#  网络源拉取（单个 URL）
# ─────────────────────────────────────────────
def fetch_web_sources(url: str) -> list[str]:
    try:
        ua = random.choice(UA_POOL)
        headers = {
            'User-Agent': ua,
            'Accept': 'text/plain,text/html,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Referer': REFERER,
        }
        proxies = {'http': PROXY, 'https': PROXY} if PROXY else None
        timeout = (15, 90) if "githubusercontent" in url else (15, 60)
        resp = None
        for retry in range(5):
            try:
                # 不使用 stream=True，让 requests 自动处理内容解压与编码
                resp = requests.get(
                    url, headers=headers, timeout=timeout,
                    verify=False, proxies=proxies, allow_redirects=True
                )
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if retry == 4:
                    raise
                time.sleep(random.uniform(1, 3))
        # 优先使用 response 声明的编码，回退 utf-8
        resp.encoding = resp.apparent_encoding or 'utf-8'
        text_content = resp.text
        lines = [l.strip() for l in text_content.splitlines() if l.strip()]
        has_m3u = any('#EXTM3U' in l.upper() for l in lines[:10])
        if has_m3u:
            parsed = parse_m3u(lines)
        else:
            parsed = []
            for line in lines:
                if ',' not in line:
                    continue
                parts = line.split(',', 1)
                name_part, url_part = parts[0].strip(), parts[1].strip()
                if 'http' not in url_part:
                    continue
                parsed.append(f"{name_part},{url_part}")
        # URL 去重
        unique, seen = [], set()
        for item in parsed:
            if ',' not in item:
                continue
            _, u = item.split(',', 1)
            fp = get_url_fingerprint(u.strip())
            if fp not in seen:
                seen.add(fp)
                unique.append(item)
        logger.info(f"✅ 拉取成功: {url} | 去重后 {len(unique)} 条")
        return unique
    except Exception as e:
        logger.error(f"❌ 拉取失败 {url}: {e}")
        return []
# ─────────────────────────────────────────────
#  本地文件读取
# ─────────────────────────────────────────────
def read_local_file(input_file: str) -> list[str]:
    try:
        with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if any(l.startswith('#EXTM3U') for l in lines[:10]):
            return parse_m3u(lines)
        parsed = []
        for l in lines:
            if ',' not in l or '://' not in l:
                continue
            parts = l.split(',', 1)
            name, url = parts[0].strip(), parts[1].strip()
            if name and url:
                parsed.append(f"{name},{url}")
        return parsed
    except FileNotFoundError:
        logger.warning(f"本地文件不存在: {input_file}")
        return []
    except Exception as e:
        logger.error(f"读取本地文件失败: {e}")
        return []
# ─────────────────────────────────────────────
#  将解析后的行添加到 domain_lines（去重）
# ─────────────────────────────────────────────
def _add_lines(raw_lines: list[str], seen_fp: set, domain_lines: dict) -> None:
    for l in raw_lines:
        if ',' not in l:
            continue
        name_part, url_part = l.split(',', 1)
        url = url_part.strip()
        fp = get_url_fingerprint(url)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        cn = clean_name(name_part.strip())
        if not cn:
            continue
        host = urlparse(url).hostname or "unknown"
        domain_lines[host].append(f"{cn},{url}")
# ─────────────────────────────────────────────
#  单个流检测（ffprobe + HTTP 兜底）
# ─────────────────────────────────────────────
def check(line: str, proxy: str = None, debug: bool = False,
          timeout_cn: int = TIMEOUT_CN, timeout_overseas: int = TIMEOUT_OVERSEAS) -> dict:
    # 提前初始化，避免异常时 locals() 取值
    name, url, overseas = '未知频道', '', False
    try:
        name, url = [x.strip() for x in line.split(',', 1)]
        overseas  = is_overseas(name)
        timeout   = timeout_overseas if overseas else timeout_cn
        start     = time.time()
        UA        = random.choice(UA_POOL)
        parsed_url = urlparse(url)
        domain    = f"{parsed_url.scheme}://{parsed_url.netloc}"
        host      = parsed_url.hostname or ""
        proxies   = {'http': proxy, 'https': proxy} if proxy else None
        if FILTER_PRIVATE_IP and is_private_ip(host):
            if debug:
                logger.debug(f"过滤内网源: {name} | {url}")
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": "内网/本地地址"}
        if REQUEST_JITTER:
            time.sleep(random.uniform(0.05, 0.2))
        headers_str = f'User-Agent: {UA}\r\nReferer: {domain}\r\nOrigin: {domain}\r\n'
        final_result = None
        for retry in range(RETRY_COUNT + 1):
            if retry > 0 and debug:
                logger.debug(f"🔄 {name} 第{retry}次重试")
            probe_size   = '5000000'  if retry == 0 else '15000000'
            analyze_dur  = '10000000' if retry == 0 else '30000000'
            cmd = [
                'ffprobe',
                '-headers',          headers_str,
                '-v',                'error',
                '-show_entries',     'stream=codec_type:format=duration,format_name',
                '-probesize',        probe_size,
                '-analyzeduration',  analyze_dur,
                '-timeout',          str(int(timeout * 1_000_000)),
                '-reconnect',        '3',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                '-err_detect',       'ignore_err',
                '-fflags',           'nobuffer+flush_packets+genpts',
                '-flags',            'low_delay',
                '-strict',           '-2',
                '-allowed_extensions', 'ALL',
                '-user_agent',       UA,
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
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                    proc.communicate()
                if debug:
                    logger.debug(f"⏱️  {name} 检测超时")
                continue
            except Exception as e:
                if proc:
                    proc.kill()
                    proc.communicate()
                if debug:
                    logger.debug(f"❌ {name} ffprobe异常: {e}")
                continue
            has_fatal  = any(kw in stderr_content for kw in FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_content or 'codec_type=audio' in stdout_content
            has_format = 'format_name=' in stdout_content
            if not has_fatal and (has_stream or has_format):
                lat = round(time.time() - start, 2)
                final_result = {"status": "有效", "name": name, "url": url, "lat": lat, "overseas": overseas}
                break
            if has_fatal:
                if debug:
                    logger.debug(f"❌ {name} 致命错误: {stderr_content[:200]}")
                break
        # HTTP 兜底检测
        if not final_result:
            try:
                req_headers = {'User-Agent': UA, 'Referer': domain, 'Origin': domain}
                resp = requests.head(url, headers=req_headers, timeout=10,
                                     allow_redirects=True, proxies=proxies, verify=False)
                if resp.status_code in (200, 206, 301, 302, 304):
                    lat = round(time.time() - start, 2)
                    final_result = {"status": "有效", "name": name, "url": url, "lat": lat, "overseas": overseas}
                elif resp.status_code == 405:
                    resp = requests.get(url, headers=req_headers, timeout=10,
                                        allow_redirects=True, proxies=proxies,
                                        verify=False, stream=True)
                    next(resp.iter_content(1024), None)
                    resp.close()
                    if resp.status_code in (200, 206, 301, 302, 304):
                        lat = round(time.time() - start, 2)
                        final_result = {"status": "有效", "name": name, "url": url, "lat": lat, "overseas": overseas}
            except Exception as e:
                if debug:
                    logger.debug(f"❌ {name} HTTP兜底失败: {e}")
        return final_result or {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": "所有检测均失败"}
    except Exception as e:
        if debug:
            logger.error(f"check() 异常 [{name}]: {e}")
        return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": str(e)}
# ─────────────────────────────────────────────
#  原子写入辅助
# ─────────────────────────────────────────────
def atomic_write(path: str, content: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)   # 原子替换，防止写入中断导致文件损坏
# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def main():
    args = parse_args()
    # 允许命令行覆盖全局配置
    global DEBUG_MODE, PROXY, TIMEOUT_CN
    DEBUG_MODE = args.debug or DEBUG_MODE
    PROXY      = args.proxy or PROXY
    if args.timeout:
        TIMEOUT_CN = args.timeout
    # 重新初始化 logger（可能 debug 模式变化）
    global logger
    logger = init_logger(DEBUG_MODE)
    input_file  = args.input  or INPUT_FILE
    output_file = args.output or OUTPUT_FILE
    if not pre_check_env(input_file, output_file):
        return
    seen_fp      = set()
    domain_lines = defaultdict(list)
    # ── 本地文件 ──
    local_lines = read_local_file(input_file)
    _add_lines(local_lines, seen_fp, domain_lines)
    logger.info(f"本地文件读取完成，当前去重后 {sum(len(v) for v in domain_lines.values())} 条")
    # ── 网络源（并发拉取）──
    if WEB_SOURCES and not args.no_web:
        logger.info(f"开始并发拉取 {len(WEB_SOURCES)} 个网络源（{FETCH_WORKERS} 线程）...")
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
            future_map = {ex.submit(fetch_web_sources, u): u for u in WEB_SOURCES}
            for fut in as_completed(future_map):
                _add_lines(fut.result(), seen_fp, domain_lines)
        logger.info(f"网络源拉取完成，当前去重后 {sum(len(v) for v in domain_lines.values())} 条")
    # ── 打散（同域名不连续，避免集中压测单服务器）──
    lines_to_check = []
    for host_lines in domain_lines.values():
        random.shuffle(host_lines)
        lines_to_check.extend(host_lines)
    random.shuffle(lines_to_check)
    total = len(lines_to_check)
    if total == 0:
        logger.error("没有有效待测源，退出")
        return
    overseas_total = sum(1 for ln in lines_to_check if is_overseas(ln.split(',', 1)[0]))
    cn_total = total - overseas_total
    logger.info(f"待测源: {total} 条 | 境内 {cn_total} | 境外 {overseas_total}")
    # ── 并发测活 ──
    cat_map     = {c: [] for c in CATEGORY_ORDER}
    fail_list   = []
    valid_count = valid_overseas = valid_cn = other_count = 0
    real_workers = min(args.workers, total)
    logger.info(f"启动测活，并发: {real_workers}")
    with ThreadPoolExecutor(max_workers=real_workers) as ex, \
         tqdm(total=total, desc="测活中", unit="源") as pbar:
        futures = {
            ex.submit(check, ln, PROXY, DEBUG_MODE, TIMEOUT_CN, TIMEOUT_OVERSEAS): ln
            for ln in lines_to_check
        }
        for fut in as_completed(futures):
            r = fut.result()
            pbar.update(1)
            if r["status"] == "有效":
                valid_count += 1
                if r["overseas"]:
                    valid_overseas += 1
                else:
                    valid_cn += 1
                cat = get_category(r["name"])
                if cat and cat in cat_map:
                    cat_map[cat].append(r)
                else:
                    other_count += 1
                pbar.set_postfix({"有效率": f"{valid_count / pbar.n * 100:.1f}%"})
            else:
                if ARCHIVE_FAIL:
                    fail_list.append(f"{r['name']},{r['url']} | 原因: {r.get('reason', '未知')}")
    # ── 写入结果（原子写入）──
    overseas_rate = f"{valid_overseas / overseas_total * 100:.1f}%" if overseas_total else "0.0%"
    cn_rate       = f"{valid_cn / cn_total * 100:.1f}%"             if cn_total       else "0.0%"
    buf = []
    buf.append(
        f"// 更新: {time.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"有效 {valid_count}/{total} | "
        f"境内 {valid_cn}/{cn_total}({cn_rate}) | "
        f"境外 {valid_overseas}/{overseas_total}({overseas_rate}) | "
        f"未分类 {other_count}\n\n"
    )
    for cat in CATEGORY_ORDER:
        items = cat_map.get(cat, [])
        if not items:
            continue
        buf.append(f"{cat},#genre#\n")
        grouped = {}
        for item in items:
            grouped.setdefault(item['name'], []).append(item)
        for ch_name in sorted(grouped, key=lambda n: min(x['lat'] for x in grouped[n])):
            best = sorted(grouped[ch_name], key=lambda x: x['lat'])[:MAX_LINKS_PER_NAME]
            for s in best:
                buf.append(f"{s['name']},{s['url']}\n")
        buf.append("\n")
    atomic_write(output_file, "".join(buf))
    if ARCHIVE_FAIL and fail_list:
        fail_buf = (
            f"// 失效源 | {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(fail_list)} 条\n\n"
            + "\n".join(fail_list) + "\n"
        )
        atomic_write(FAIL_FILE, fail_buf)
    logger.info("=" * 70)
    logger.info(f"完成！结果保存至: {output_file}")
    logger.info(f"整体有效率：{valid_count}/{total} = {valid_count / total * 100:.1f}%")
    logger.info(f"境内：{valid_cn}/{cn_total} = {cn_rate}")
    logger.info(f"境外：{valid_overseas}/{overseas_total} = {overseas_rate}")
    logger.info("=" * 70)
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()