# ====================== 最顶部先执行警告屏蔽，拦截所有导入阶段的警告 ======================
import warnings
warnings.filterwarnings('ignore')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ====================== 所有模块导入放在警告屏蔽之后 ======================
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import time
import os
import re
import random
import multiprocessing
from urllib.parse import urlparse, unquote, parse_qs, urlencode
from tqdm import tqdm
import requests
import chardet
import logging
from collections import defaultdict
# -------------------------- 核心配置项（优化关键参数） --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "paste.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "live_ok.txt")
FAIL_FILE = os.path.join(BASE_DIR, "live_fail.txt")
LOG_FILE = os.path.join(BASE_DIR, "iptv_check.log")
# 基础功能开关：默认开启调试日志，便于排查
DEBUG_MODE = True
AUTO_BACKUP = True
ARCHIVE_FAIL = True
SORT_BY_LATENCY_FIRST = True
# 并发&防封禁配置：延长超时，增加重试
MAX_WORKERS = 12
MAX_PER_DOMAIN_WORKERS = 2
TIMEOUT_CN = 30
TIMEOUT_OVERSEAS = 60
RETRY_COUNT = 3
REQUEST_JITTER = True
# 源筛选配置
MAX_LINKS_PER_NAME = 5
FILTER_PRIVATE_IP = True
REMOVE_REDUNDANT_PARAMS = False
# 网络源列表（已删除失效 xnkl.txt）
WEB_SOURCES = [
    "https://feer-cdn-bp.xpnb.qzz.io/xnkl.txt",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
    "https://raw.githubusercontent.com/Jsnzkpg/Jsnzkpg/Jsnzkpg/Jsnzkpg1",
]
# UA池、REFERER、BLACKLIST 等保持原样（省略以节省篇幅，实际代码中不变）
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
    'PotPlayer/230502 (Windows NT 10.0; x64)'
           ]  # 原 UA_POOL 全部保留
REFERER = 'https://www.baidu.com'
BLACKLIST = ["购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", "教程", "联系", "推广", "免费"]
OVERSEAS_KEYWORDS = [
    "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
    "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
    "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
    "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "beIN"
]
FATAL_ERROR_KEYWORDS = [
    "404 not found", "403 forbidden", "500 internal server error",
    "connection timed out", "could not resolve host", "connection refused",
    "no route to host", "network unreachable", "name or service not known",
    "unable to open file", "invalid url", "protocol not found",
    "server returned 404", "server returned 403", "server returned 500",
    "host unreachable", "dns resolution failed", "empty reply from server"
]
PROXY = None  #  'https://127.0.0.1:7897' 
# -------------------------- 日志系统初始化（保持不变） --------------------------
# ...（OVERSEAS_KEYWORDS、FATAL_ERROR_KEYWORDS、PROXY 等全部保持原样）
# -------------------------- 日志系统初始化（保持不变） --------------------------
def init_logger():
    logger = logging.getLogger("IPTV_CHECK")
    logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='w')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    file_handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    console_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
logger = init_logger()
def simplify(text):
    trad = '衛視廣東體樂電影劇國際臺灣鳳凰翡翠亞畫愛爾達動兒龍粵華線衛星電視綜藝娛樂新聞財經購物備用測試福利廣告下線加群提示教程聯繫用戶會員使用推廣進群免費切勿音樂體育運動籃球賽馬跑馬電影影視劇影院動畫卡通兒童紀實探索發現紀錄百姓生活法制政法兵器國防旅遊健康養生動物科教教育壹緯歷史島傳奇綜合東財經專區資訊寶數碼粵語發現東森三立緯来八大年代非凡中天華視台視中視民視龍祥靖天'
    simp = '卫视广东体乐电影剧国际台湾凤凰翡翠亚画爱尔达动儿龙粤华线卫星电视综艺娱乐新闻财经购物备用测试福利广告下线加群提示教程联系用户会员使用推广进群免费切勿音乐体育运动篮球赛马跑马电影影视剧影院动画卡通儿童纪实探索发现纪录百姓生活法制政法兵器国防旅游健康养生动物科教教育一纬历史岛传奇综合东财经专区资讯宝数码粤语发现东森三立纬来八大年代非凡中天华视台视中视民视龙祥靖天'
    table = str.maketrans(trad, simp)
    return text.translate(table).upper().strip()

# 核心修改：乱码转换优先UTF-8（含utf-8-sig），明确解码优先级
def fix_mojibake(text):
    if not text or not text.strip():
        return text
    
    # 移除无效字符
    invalid_chars = re.compile(
        r'[\uE000-\uF8FF\u2600-\u27BF\u0000-\u001F\u007F-\u009F\U0001F000-\U0001FFFF]',
        re.UNICODE
    )
    text = invalid_chars.sub('', text)
    text = re.sub(r'[-—_～•·:·\s]{2,}', ' ', text).strip()
    
    # 尝试URL解码
    try:
        text = unquote(text)
    except:
        pass
    
    text_bytes = text.encode('utf-8', errors='ignore')
    best_text = text
    min_chinese_ratio = 0.3

    # 优先尝试UTF-8系列编码（核心修改：提升UTF-8优先级）
    utf8_encodings = ['utf-8-sig', 'utf-8']
    for enc in utf8_encodings:
        try:
            utf8_text = text_bytes.decode(enc, errors='strict')
            chinese_count = sum('\u4e00' <= c <= '\u9fff' for c in utf8_text)
            utf8_ratio = chinese_count / len(utf8_text) if len(utf8_text) > 0 else 0
            if utf8_ratio >= min_chinese_ratio:
                best_text = utf8_text
                # 找到有效UTF-8解码直接返回
                fixed_text = invalid_chars.sub('', best_text).strip()
                return fixed_text or text
        except UnicodeDecodeError:
            continue

    # UTF-8解码失败后，再尝试其他编码
    support_encodings = ['gb18030', 'gbk', 'big5']
    detected_encoding = chardet.detect(text_bytes)['encoding']
    if detected_encoding and detected_encoding.lower() not in [e.lower() for e in support_encodings + utf8_encodings]:
        support_encodings.append(detected_encoding)
    support_encodings.append('latin-1')

    best_ratio = sum('\u4e00' <= c <= '\u9fff' for c in best_text) / len(best_text) if best_text else 0
    for enc in support_encodings:
        try:
            temp_text = text_bytes.decode(enc, errors='strict')
            temp_chinese = sum('\u4e00' <= c <= '\u9fff' for c in temp_text)
            temp_ratio = temp_chinese / len(temp_text) if len(temp_text) > 0 else 0
            if temp_ratio > best_ratio:
                best_text = temp_text
                best_ratio = temp_ratio
        except:
            continue

    fixed_text = invalid_chars.sub('', best_text).strip()
    return fixed_text or text

def clean_name(n):
    n = fix_mojibake(n)
    if not n:
        return "未知频道"
    n = re.sub(r'\[.*?\]|（.*?）|\(.*?\)|\{.*?\}|【.*?】|《.*?》', '', n)
    n = re.sub(r'(?i)CCTV\s*[-—_～•·:·\s]*(\d{1,2})(\+)?', r'CCTV\1\2', n)
    if not re.search(r'(?i)4K|8K|超高清', n):
        m = re.search(r'(?i)(CCTV\d{1,2}\+?)', n)
        if m:
            return m.group(1).upper()
    n = re.sub(r'(?i)[-_—～•·:·\s]|HD|高清|超清|超高清|标清', '', n)
    n = re.sub(r'(?i)直播|主线|台$', '', n)
    n = re.sub(r'央视(\d{1,2})', r'CCTV\1', n)
    n = re.sub(r'中央(\d{1,2})', r'CCTV\1', n)
    return simplify(n)

def get_category(name):
    s = simplify(name)
    if any(k in s for k in BLACKLIST):
        return None
    if any(k in s for k in ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"]):
        return "4K/8K專區"
    if any(k in s for k in ["CCTV", "中央", "央视"]):
        return "央視頻道"
    if "卫视" in s:
        return "各地衛視"
    sport_keywords = [
        "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球", "台球", "棋", "赛马",
        "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技", "SPORT", "SPOTV", "BALL", "晴彩", "咪咕",
        "NBA", "英超", "西甲", "意甲", "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J联赛",
        "K联赛", "美职", "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
        "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运", "亚运", "世界杯",
        "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA", "五大联赛", "Pac-12", "大学体育", "文体"
    ]
    if any(k in s for k in sport_keywords):
        return "體育賽事"
    music_keywords = [
        "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV", "流行", "嘻哈", "摇滚",
        "古典", "爵士", "民谣", "电音", "EDM", "纯音乐", "伴奏", "Karaoke", "首",
        "Channel V", "Trace", "VH1", "MTV Hits", "MTV Live", "KKBOX", "韩国女团", "女团",
        "Space Shower", "KAYOPOPS", "Musicon"
    ]
    if any(k in s for k in music_keywords):
        return "音樂頻道"
    kids_anime_keywords = ["卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼儿", "宝宝", "宝贝", "炫动", "酷",
                           "炫酷", "卡通片", "动漫片", "动画片", "小公", "CARTOON", "ANIME", "ANIMATION", "KIDS",
                           "睛彩青少", "青少",
                           "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS", "TOON", "BOOMERANG", "尼克"]
    if any(k in s for k in kids_anime_keywords):
        return "少兒動漫"
    movie_keywords = [
        "至臻", "爱奇艺", "爆谷", "HBO", "POPC", "邵氏", "娱乐", "经典", "戏", "黄金", "亚洲",
        "MOVIE", "SERIES", "天映", "黑莧", "龙华", "片", "偶像", "影剧", "映画", "影迷", "华语",
        "新视觉", "好莱坞", "采昌", "美亚", "纬来", "ASTRO", "剧集", "电影", "影院", "影视",
        "剧场", "STAR", "SHORTS", "NETFLIX", "Prime", "Disney+", "Paramount+", "电视剧",
        "Peacock", "Max", "Showtime", "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime",
        "Hallmark", "华纳", "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
        "Marvel", "DCU", "Star Wars", "剧场版", "纪录片", "真人秀", "综艺", "真人实境",
        "DLIFE", "NECO", "The Cinema", "家庭剧场", "Homedrama", "Family Gekijo", "Entermei Tele"
    ]
    if any(k in s for k in movie_keywords):
        return "影視劇集"
    overseas_keywords = [
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
        "RIA", "QJ", "OKEY", "NOW", "NOW财经", "NOW新闻", "NHKWORLD", "NET", "MTLIVE", "METRTV",
        "MEDICIARTS", "MEDICARTS", "LIFETIME", "LIFETIM", "KPLUS", "KOMPASTV", "KMTV", "KBSWORLD",
        "INEWS", "INDOSIAR", "HUAHEEDAI", "HOY资讯", "HOYINFOTAINMENT", "HOY78", "HOY77", "HOY76",
        "HKS", "HITS", "HGT", "HB强档", "HB家庭", "GTVVARIETY", "GTVDRAMA", "GOOD福音2", "GOODTV福音",
        "GLOBALTREKKER", "FTV新闻", "FTVONE", "FTV", "FASHIONTV2", "EVE", "EUROSPOR", "EURONEWS",
        "EBCSUPERTV", "EBCFINANCIAL新闻", "DAZ1", "CTI新闻+", "CTITVVARIETY", "COLORSTAMIL", "有线",
        "CNN印尼", "CNBC", "CITRA", "CINEMAX", "CINEMAWORLD", "CHU", "CH8", "CH5", "BT", "BLTV",
        "BERNAMANEWS", "BBCWORLD", "BBCBEEBIES", "B4UMUSIC", "AXN", "AWESOME", "AWESOM", "AWANI",
        "ARENABOLA", "AOD", "ANIMAX", "ANIMALPLANET", "ANIMALPLANE", "ALJAZEERA", "AFN", "AF", "AEC",
        "8TV", "联合国", "UNTV", "联合国 UNTV", "耀才财经", "TVBJ1", "TVBD", "TVBASIANDRAMA", "TVB1", "TV9"
    ]
    if any(k in s for k in overseas_keywords):
        return "港澳台境外"
    return "其他頻道"

def is_overseas(name):
    s = simplify(name).upper()
    return any(kw.upper() in s for kw in OVERSEAS_KEYWORDS)

def is_private_ip(host):
    if not host:
        return True
    private_pattern = re.compile(
        r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|::1|fc00:|fe80:|localhost|0\.0\.0\.0)'
    )
    return bool(private_pattern.match(host))

def clean_url_params(url):
    if not REMOVE_REDUNDANT_PARAMS:
        return url
    try:
        parsed = urlparse(url)
        keep_params = ['codec', 'resolution', 'bitrate', 'stream', 'channel', 'id', 'pid', 'u', 'token', 'key']
        query_dict = parse_qs(parsed.query, keep_blank_values=True)
        filtered_query = {k: v for k, v in query_dict.items() if any(kw in k.lower() for kw in keep_params)}
        new_url = parsed._replace(query=urlencode(filtered_query, doseq=True)).geturl()
        return new_url
    except:
        return url

def get_url_fingerprint(url):
    try:
        cleaned_url = clean_url_params(url)
        p = urlparse(cleaned_url)
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        path = p.path
        query = p.query
        return f"{host}{port}{path}{query or ''}".lower()
    except:
        return url.lower()

# -------------------------- 环境预检（保持不变） --------------------------
def pre_check_env():
    logger.info("🔍 开始环境预检...")
    try:
        proc = subprocess.run(
            ['ffprobe', '-version'], capture_output=True, timeout=10, shell=False
        )
        if proc.returncode != 0:
            logger.error("❌ 环境预检失败：未找到ffprobe，请安装ffmpeg并配置到系统环境变量")
            return False
        logger.info("✅ ffprobe环境正常")
    except FileNotFoundError:
        logger.error("❌ 环境预检失败：未找到ffprobe，请安装ffmpeg并配置到系统环境变量")
        return False
    except Exception as e:
        logger.error(f"❌ ffprobe检查异常：{str(e)}")
        return False
    if not os.path.exists(INPUT_FILE) and not WEB_SOURCES:
        logger.warning("⚠️  本地输入文件不存在，且无配置网络源，仅能检测网络源")
    elif os.path.exists(INPUT_FILE):
        logger.info(f"✅ 本地输入文件正常: {INPUT_FILE}")
    if AUTO_BACKUP and os.path.exists(OUTPUT_FILE):
        backup_file = OUTPUT_FILE.replace('.txt', f'_backup_{time.strftime("%Y%m%d_%H%M%S")}.txt')
        try:
            os.rename(OUTPUT_FILE, backup_file)
            logger.info(f"✅ 上一次结果已备份: {backup_file}")
        except Exception as e:
            logger.warning(f"⚠️  结果备份失败: {str(e)}")
    logger.info("✅ 环境预检全部通过，开始执行检测\n")
    return True

# -------------------------- 核心测活函数（保持不变） --------------------------
def check(line):
    try:
        name, url = [x.strip() for x in line.split(",", 1)]
        overseas = is_overseas(name)
        timeout = TIMEOUT_OVERSEAS if overseas else TIMEOUT_CN
        start = time.time()
        UA = random.choice(UA_POOL)
        parsed_url = urlparse(url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        host = parsed_url.hostname or ""
        if FILTER_PRIVATE_IP and is_private_ip(host):
            if DEBUG_MODE:
                logger.debug(f"过滤内网源: {name} | {url}")
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": "内网/本地地址"}
        if REQUEST_JITTER:
            time.sleep(random.uniform(0.05, 0.2))
        headers_str = f'User-Agent: {UA}\r\nReferer: {domain}\r\nOrigin: {domain}\r\n'
        proxies = {'http': PROXY, 'https': PROXY} if PROXY else None
        final_result = None
        for retry in range(RETRY_COUNT + 1):
            if retry > 0 and DEBUG_MODE:
                logger.debug(f"🔄 {name} 第{retry}次重试")
            cmd = [
                'ffprobe',
                '-headers', headers_str,
                '-v', 'error',
                '-show_entries', 'stream=codec_type:format=duration,format_name',
                '-probesize', '5000000' if retry == 0 else '15000000',
                '-analyzeduration', '10000000' if retry == 0 else '30000000',
                '-timeout', str(int(timeout * 1000000)),
                '-reconnect', '3',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                '-err_detect', 'ignore_err',
                '-fflags', 'nobuffer+flush_packets+genpts',
                '-flags', 'low_delay',
                '-strict', '-2',
                '-allowed_extensions', 'ALL',
                '-user_agent', UA,
            ]
            if PROXY:
                cmd.extend(['-http_proxy', PROXY])
            cmd.append(url)
            proc = None
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
                stdout, stderr = proc.communicate(timeout=timeout + 5)
                returncode = proc.returncode
                stdout_content = stdout.decode('utf-8', errors='ignore').lower()
                stderr_content = stderr.decode('utf-8', errors='ignore').lower()
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                    proc.communicate()
                if DEBUG_MODE:
                    logger.debug(f"⏱️  {name} 检测超时")
                continue
            except Exception as e:
                if proc:
                    proc.kill()
                    proc.communicate()
                if DEBUG_MODE:
                    logger.debug(f"❌ {name} ffprobe执行异常: {str(e)}")
                continue
            has_fatal_error = any(kw in stderr_content for kw in FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_content or 'codec_type=audio' in stdout_content
            has_format = 'format_name=' in stdout_content
            if not has_fatal_error and (has_stream or has_format):
                latency = round(time.time() - start, 2)
                final_result = {"status": "有效", "name": name, "url": url, "lat": latency, "overseas": overseas}
                break
            if has_fatal_error:
                if DEBUG_MODE:
                    logger.debug(f"❌ {name} 致命错误: {stderr_content[:200]}")
                break
        if not final_result:
            try:
                resp = requests.head(
                    url, headers={'User-Agent': UA, 'Referer': domain, 'Origin': domain},
                    timeout=10, allow_redirects=True, proxies=proxies, verify=False
                )
                if resp.status_code in [200, 206, 301, 302, 304]:
                    latency = round(time.time() - start, 2)
                    final_result = {"status": "有效", "name": name, "url": url, "lat": latency, "overseas": overseas}
                elif resp.status_code == 405:
                    resp = requests.get(
                        url, headers={'User-Agent': UA, 'Referer': domain, 'Origin': domain},
                        timeout=10, allow_redirects=True, proxies=proxies, verify=False, stream=True
                    )
                    next(resp.iter_content(1024), None)
                    resp.close()
                    if resp.status_code in [200, 206, 301, 302, 304]:
                        latency = round(time.time() - start, 2)
                        final_result = {"status": "有效", "name": name, "url": url, "lat": latency, "overseas": overseas}
            except Exception as e:
                if DEBUG_MODE:
                    logger.debug(f"❌ {name} HTTP兜底检测失败: {str(e)}")
        if final_result:
            return final_result
        else:
            return {"status": "失效", "name": name, "url": url, "overseas": overseas, "reason": "所有检测均失败"}
    except Exception as e:
        _name = locals().get('name', '未知频道')
        _overseas = locals().get('overseas', False)
        if DEBUG_MODE:
            logger.error(f"Error checking {_name}: {e}")
        return {"status": "失效", "name": _name, "url": locals().get('url', ''), "overseas": _overseas, "reason": str(e)}

# -------------------------- M3U解析/文件读取（核心优化解析和乱码转换流程） --------------------------
def parse_m3u(lines):
    """优化M3U解析：处理EXTINF和URL之间的空白行，输出影视仓格式（频道名,URL）"""
    parsed = []
    extinf_line = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 匹配EXTINF行（支持带时长和不带时长的格式）
        if re.match(r'^#EXTINF:\-?\d+,', line):
            extinf_line = line
            continue
        # 遇到URL且之前有EXTINF行，立即匹配
        if extinf_line and (line.startswith('http://') or line.startswith('https://')):
            display_name = re.search(r',(.*)$', extinf_line)
            display_name = display_name.group(1).strip() if display_name else '未知频道'
            # 统一进行乱码转换（优先UTF-8）
            display_name = fix_mojibake(display_name)
            parsed.append(f"{display_name},{line}")
            extinf_line = None  # 重置，准备下一个匹配
    return parsed
def fetch_web_sources(url):
    """核心优化：所有网页源先解析为影视仓格式（频道名,URL），再统一乱码转换"""
    try:
        ua = random.choice(UA_POOL)
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Referer': REFERER,
        }
        proxies = {'http': PROXY, 'https': PROXY} if PROXY else None
        resp = None
        for retry in range(5):
            try:
                resp = requests.get(
                    url, 
                    headers=headers,
                    timeout=(15, 90) if "githubusercontent" in url else (15, 60),
                    verify=False, 
                    stream=True, 
                    proxies=proxies, 
                    allow_redirects=True
                )
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if retry == 4:
                    raise
                time.sleep(random.uniform(1, 3))
        
        content = resp.content
        logger.debug(f"📥 拉取 {url} 成功，原始内容长度: {len(content)} 字节")
        
        # 解压
        try:
            if len(content) >= 2 and content[:2] == b'\x1f\x8b':
                import gzip
                content = gzip.decompress(content)
        except: pass
        try:
            if len(content) >= 3 and content[:3] == b'\x0b\x18\x00':
                import brotli
                content = brotli.decompress(content)
        except: pass
        
        # 解码优化
        text_content = None
        # 强制优先 UTF-8 + replace 容错
        try:
            text_content = content.decode('utf-8', errors='replace')
            logger.debug("✅ 强制使用 utf-8 + replace 解码")
        except:
            pass
        
        if not text_content:
            for enc in ['utf-8-sig', 'gb18030', 'gbk', 'big5', 'latin-1']:
                try:
                    text_content = content.decode(enc, errors='replace')  # 用 replace 代替 ignore
                    logger.debug(f"✅ 使用 {enc} + replace 解码成功")
                    break
                except:
                    continue
        
        if not text_content:
            text_content = content.decode('utf-8', errors='replace')
            logger.warning("兜底 utf-8 replace")
        
        # 预处理（保留 M3U 头）
        lines = []
        for line in text_content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(('#', '//', '/*', '*/')) and not line.startswith(('#EXTINF:', '#EXTM3U', '#EXTVLCOPT')):
                continue
            lines.append(line)
        logger.debug(f"📝 预处理后剩余 {len(lines)} 行内容")
        
        # 统一解析
        parsed = []
        if any(l.strip().startswith('#EXTM3U') for l in lines):
            parsed = parse_m3u(lines)
        else:
            parsed_count = 0
            skipped_count = 0
            for line in lines:
                line = line.strip()
                if not line:
                    skipped_count += 1
                    continue
                
                # 显式跳过分组标题，减少日志噪音
                if '#genre#' in line.lower() or line.endswith('#genre#'):
                    skipped_count += 1
                    continue
                
                if ',' not in line:
                    # 只在 DEBUG_MODE 下打印少量示例，避免刷屏
                    if DEBUG_MODE and skipped_count < 10:
                        logger.debug(f"跳过无逗号行: {line[:80]}...")
                    skipped_count += 1
                    continue
                
                parts = line.split(',', 1)
                if len(parts) != 2:
                    skipped_count += 1
                    continue
                
                name_part = parts[0].strip()
                url_part = parts[1].strip()
                
                # 更宽松的 URL 检查
                if 'http://' not in url_part and 'https://' not in url_part:
                    if DEBUG_MODE and skipped_count < 10:
                        logger.debug(f"URL 无 http(s):// : {url_part[:80]}...")
                    skipped_count += 1
                    continue
                
                raw_name = fix_mojibake(name_part) or "未知频道"
                parsed.append(f"{raw_name},{url_part}")
                parsed_count += 1
            
            logger.info(f"纯文本解析结果：成功 {parsed_count} 条 | 跳过 {skipped_count} 条 | 总行 {len(lines)}")
        
        # 去重（原版逻辑 + 防错保护，彻底杜绝 set.items 错误）
        unique_parsed = []
        seen_urls = set()
        for item in parsed:
            if "," not in item:
                continue
            try:
                name, url = item.split(",", 1)
                url_finger = get_url_fingerprint(url)
                if url_finger not in seen_urls:
                    seen_urls.add(url_finger)
                    unique_parsed.append(item)
            except Exception:
                continue
        
        logger.info(f"✅ 拉取成功: {url} | 原始{len(parsed)}条 | 去重后{len(unique_parsed)}条源（影视仓格式）")
        return unique_parsed
    except Exception as e:
        logger.error(f"❌ 拉取失败 {url}: {str(e)}")
        return []
# -------------------------- read_local_file（保持不变） --------------------------
def read_local_file():
    """本地文件读取：统一转换为影视仓格式并优先UTF-8乱码转换"""
    try:
        with open(INPUT_FILE, 'rb') as f:
            content = f.read()
        text = None
        # 核心修改：优先UTF-8系列解码
        encode_priority = ['utf-8-sig', 'utf-8', 'gb18030', 'gbk', 'big5']
        for enc in encode_priority:
            try:
                text = content.decode(enc, errors='strict')
                logger.info(f"✅ 使用编码 {enc} 成功读取本地文件（优先UTF-8）")
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            logger.warning("⚠️  所有编码严格解码失败，使用UTF-8兼容模式读取")
            text = content.decode('utf-8', errors='ignore')
        lines = text.splitlines()
        parsed_lines = []
        if any(l.strip().startswith('#EXTM3U') for l in lines):
            # M3U格式解析为影视仓格式
            parsed_lines = parse_m3u(lines)
        else:
            # 纯文本格式：逐行处理并乱码转换
            for l in lines:
                l = l.strip()
                if not l or "," not in l or "://" not in l:
                    continue
                parts = l.split(",", 1)
                if len(parts) != 2:
                    continue
                raw_name_part, url_part = parts[0].strip(), parts[1].strip()
                if not raw_name_part or not url_part:
                    continue
                # 统一乱码转换（优先UTF-8）
                raw_name = fix_mojibake(raw_name_part)
                parsed_lines.append(f"{raw_name},{url_part}")
        
        # 输出本地文件解析出的源数量
        logger.info(f"📄 本地文件解析出 {len(parsed_lines)} 条有效源（影视仓格式）")
        return parsed_lines
    except FileNotFoundError:
        logger.warning(f"⚠️  本地输入文件不存在: {INPUT_FILE}")
        return []

# -------------------------- 主函数（保持不变，确认输出分类顺序） --------------------------
def main():
    # 环境预检
    if not pre_check_env():
        return
    # 1. 源数据读取&去重清洗
    seen_fp = set()
    lines_to_check = []
    domain_lines = defaultdict(list)  # 按域名分组，用于并发控制
    # 读取本地文件（已转换为影视仓格式+乱码修复）
    local_lines = read_local_file()
    for l in local_lines:
        l = l.strip()
        if not l or "," not in l or "://" not in l:
            continue
        parts = l.split(",", 1)
        if len(parts) != 2:
            continue
        raw_name_part, url_part = parts[0].strip(), parts[1].strip()
        if not raw_name_part or not url_part:
            continue
        # 再次确认乱码转换（双重保障）
        raw_name = fix_mojibake(raw_name_part)
        url = url_part
        fp = get_url_fingerprint(url)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        cn = clean_name(raw_name)
        if not cn:
            continue
        # 按域名分组
        host = urlparse(url).hostname or "unknown"
        domain_lines[host].append(f"{cn},{url}")
    # 拉取网络源（已转换为影视仓格式+乱码修复）
    if WEB_SOURCES:
        logger.info(f"🚀 开始下载 {len(WEB_SOURCES)} 个网络源...")
        for url in WEB_SOURCES:
            for l in fetch_web_sources(url):
                l = l.strip()
                if not l or "," not in l or "://" not in l:
                    continue
                parts = l.split(",", 1)
                if len(parts) != 2:
                    continue
                raw_name_part, url_part = parts[0].strip(), parts[1].strip()
                if not raw_name_part or not url_part:
                    continue
                # 再次确认乱码转换（双重保障）
                raw_name = fix_mojibake(raw_name_part)
                url = url_part
                fp = get_url_fingerprint(url)
                if fp in seen_fp:
                    continue
                seen_fp.add(fp)
                cn = clean_name(raw_name)
                if not cn:
                    continue
                host = urlparse(url).hostname or "unknown"
                domain_lines[host].append(f"{cn},{url}")
    # 域名打散，避免单域名连续请求，防封禁
    for host in domain_lines:
        random.shuffle(domain_lines[host])
        lines_to_check.extend(domain_lines[host])
    random.shuffle(lines_to_check)  # 全局打乱
    # 统计信息
    total = len(lines_to_check)
    overseas_total = sum(1 for line in lines_to_check if is_overseas(line.split(",",1)[0]))
    cn_total = total - overseas_total
    logger.info(f"🚀 待测源就绪: 共{total}条（URL去重）| 境内{cn_total}条 | 境外{overseas_total}条")
    if total == 0:
        logger.error("❌ 没有找到任何有效待测源，程序退出")
        return
    # 2. 多线程并发测活
    # 确认输出分类顺序：严格按照指定顺序
    cat_map = {c:[] for c in ["4K/8K專區", "港澳台境外", "影視劇集", "央視頻道", "各地衛視", "體育賽事", "少兒動漫", "音樂頻道", "其他頻道"]}
    fail_list = []
    valid_count = 0
    other_count = 0
    valid_overseas = 0
    valid_cn = 0
    # 自适应线程数：源数量少时降低并发，避免资源浪费
    real_workers = min(MAX_WORKERS, total)
    logger.info(f"🚀 启动测活，并发线程数: {real_workers}")
    with ThreadPoolExecutor(max_workers=real_workers) as ex, tqdm(total=total, desc="IPTV源测活中", unit="源") as p:
        futures = [ex.submit(check, ln) for ln in lines_to_check]
        for f in as_completed(futures):
            r = f.result()
            p.update(1)
            if not r:
                continue
            # 有效源处理
            if r["status"] == "有效":
                valid_count += 1
                if r.get("overseas", False):
                    valid_overseas += 1
                else:
                    valid_cn += 1
                cat = get_category(r["name"])
                if cat in cat_map:
                    cat_map[cat].append(r)
                else:
                    other_count += 1
                # 进度条实时更新有效率
                p.set_postfix({"有效率": f"{(valid_count/p.n*100):.1f}%"})
            # 失效源归档
            else:
                if ARCHIVE_FAIL:
                    fail_list.append(f"{r['name']},{r['url']} | 原因: {r.get('reason', '未知')}")
    # 3. 结果写入（严格按指定分类顺序输出）
    logger.info("📝 开始写入结果文件...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        overseas_rate = f"{(valid_overseas/overseas_total*100):.1f}%" if overseas_total > 0 else "0.0%"
        cn_rate = f"{(valid_cn/cn_total*100):.1f}%" if cn_total > 0 else "0.0%"
        f.write(f"// 更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 总有效: {valid_count}/{total} | 境内有效: {valid_cn}/{cn_total}({cn_rate}) | 境外有效: {valid_overseas}/{overseas_total}({overseas_rate}) | 未分类: {other_count}\n\n")
        # 按指定优先级输出分类（核心确认：顺序不变）
        for cat in ["4K/8K專區", "港澳台境外", "影視劇集", "央視頻道", "各地衛視", "體育賽事", "少兒動漫", "音樂頻道", "其他頻道"]:
            items = cat_map[cat]
            if not items:
                continue
            f.write(f"{cat},#genre#\n")
            grouped = {}
            for item in items:
                grouped.setdefault(item['name'], []).append(item)
            # 排序规则：优先延迟，可选稳定性
            for name in sorted(grouped, key=lambda n: min(x['lat'] for x in grouped[n])):
                best = sorted(grouped[name], key=lambda x: x['lat'])[:MAX_LINKS_PER_NAME]
                for s in best:
                    f.write(f"{s['name']},{s['url']}\n")
            f.write("\n")
    # 失效源归档
    if ARCHIVE_FAIL and fail_list:
        with open(FAIL_FILE, 'w', encoding='utf-8') as f:
            f.write(f"// 失效源归档 | 更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 共{len(fail_list)}条\n\n")
            for line in fail_list:
                f.write(f"{line}\n")
        logger.info(f"✅ 失效源已归档: {FAIL_FILE}")
    # 最终统计输出
    logger.info("="*80)
    logger.info(f"✨ 任务圆满完成！结果保存至: {OUTPUT_FILE}")
    logger.info(f"📊 整体测活率：{(valid_count/total*100):.1f}% ({valid_count}/{total})")
    logger.info(f"📊 境内测活率：{cn_rate} ({valid_cn}/{cn_total})")
    logger.info(f"📊 境外测活率：{overseas_rate} ({valid_overseas}/{overseas_total})")
    logger.info(f"📁 未分类有效源：{other_count} 条")
    logger.info("="*80)
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()