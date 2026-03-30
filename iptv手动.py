# -*- coding: utf-8 -*-
import subprocess, time, os, re, random
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "paste.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "live_ok.txt")

WEB_SOURCES = [
    "https://feer-cdn-bp.xpnb.qzz.io/xnkl.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
    "https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt"
]

MAX_WORKERS = 40
TIMEOUT = 20
MAX_LINKS_PER_NAME = 5
UA = 'Mozilla/5.0 (Linux; Android 10; TV Box) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
REFERER = 'https://www.yangshipin.cn'
PROXY = ''  # 如需使用代理，可填写 'http://127.0.0.1:7897'

BLACKLIST = ["购物","备用","测试","福利","广告","下线","加群","提示","教程","联系","推广","免费"]

def simplify(text):
    trad = '衛視廣東體樂電影劇國際臺灣鳳凰翡翠亞畫愛爾達動兒龍粵華線衛星電視綜藝娛樂新聞財經購物備用測試福利廣告下線加群提示教程聯繫用戶會員使用推廣進群免費切勿音樂體育運動籃球賽馬跑馬電影影視劇影院動畫卡通兒童紀實探索發現紀錄百姓生活法制政法兵器國防旅遊健康養生動物科教教育壹緯歷史島傳奇綜合東財經專區資訊寶數碼粵語發現東森三立緯来八大年代非凡中天華視台視中視民視龍祥靖天'
    simp = '卫视广东体乐电影剧国际台湾凤凰翡翠亚画爱尔达动儿龙粤华线卫星电视综艺娱乐新闻财经购物备用测试福利广告下线加群提示教程联系用户会员使用推广进群免费切勿音乐体育运动篮球赛马跑马电影影视剧影院动画卡通儿童纪实探索发现纪录百姓生活法制政法兵器国防旅游健康养生动物科教教育一纬历史岛传奇综合东财经专区资讯宝数码粤语发现东森三立纬来八大年代非凡中天华视台视中视民视龙祥靖天'   
    table = str.maketrans(trad, simp)
    return text.translate(table).upper().strip()

def fix_mojibake(text):
    if not text or len(text.strip()) == 0:
        return text

    priority_pairs = [
        ('utf-8', 'gbk'),  
        ('utf-8', 'gb18030'),
        ('gbk', 'utf-8'),       
        ('gb18030', 'utf-8'),
        ('latin1', 'gbk'),      
        ('latin1', 'gb18030'),
        ('big5', 'utf-8'),
        ('utf-8', 'big5'),
    ]

    original_len = len(text)
    best_candidate = text
    best_chinese_ratio = sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / max(1, original_len)

    for wrong, correct in priority_pairs:
        try:
            fixed = text.encode(wrong, errors='strict').decode(correct, errors='strict')
            chinese_count = sum(1 for c in fixed if '\u4e00' <= c <= '\u9fff')
            ratio = chinese_count / max(1, len(fixed))
            
            if (abs(len(fixed) - original_len) <= original_len * 0.3 and
                ratio > best_chinese_ratio + 0.2 and
                ratio > 0.4 and
                not any(ord(c) < 32 and c not in '\t\n\r' for c in fixed)):
                
                best_candidate = fixed
                best_chinese_ratio = ratio
                
                if ratio > 0.7:
                    return fixed.strip()
                    
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    return best_candidate.strip()

def clean_name(n):
    n = fix_mojibake(n)  # 先尝试修复乱码
    if not n: return "未知频道"
    n = re.sub(r'\[.*?\]|（.*?）|\(.*?\)|\{.*?\}|【.*?】|《.*?》', '', n)
    n = re.sub(r'(?i)CCTV\s*[-—_～•·:·\s]*(\d{1,2})(\+)?', r'CCTV\1\2', n)
    if not re.search(r'(?i)4K|8K|超高清', n):
        m = re.search(r'(?i)(CCTV\d{1,2}\+?)', n)
        if m: return m.group(1).upper()
    n = re.sub(r'(?i)[-_—～•·:·\s]|HD|高清|超清|超高清|标清', '', n)
    n = re.sub(r'(?i)直播|主线|台$', '', n)
    return simplify(n)

def get_category(name):
    s = simplify(name)
    if any(k in s for k in BLACKLIST): return None
    if any(k in s for k in ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR"]): return "4K/8K專區"
    if any(k in s for k in ["CCTV", "中央", "央视"]): return "央視頻道"
    if "卫视" in s: return "各地衛視"
    sport_keywords = [
        "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球", "台球", "棋", "赛马",
        "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技", "SPORT", "SPOTV", "BALL", "晴彩", "咪咕",
        "NBA", "英超", "西甲", "意甲", "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J联赛",
        "K联赛", "美职", "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
        "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运", "亚运", "世界杯",
        "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA", "五大联赛", "Pac-12", "大学体育"
    ]
    if any(k in s for k in sport_keywords): return "體育賽事"
    music_keywords = [
       "音乐", "歌", "MTV", "演唱会", "演唱", "点播", "CMUSIC", "KTV", "流行", "嘻哈", "摇滚",
        "古典", "爵士", "民谣", "电音", "EDM", "纯音乐", "伴奏", "Karaoke", "首",
        "Channel V", "Trace", "VH1", "MTV Hits", "MTV Live", "KKBOX", "韩国女团", "女团",
        "Space Shower", "KAYOPOPS", "Musicon"
    ]
    if any(k in s for k in music_keywords): return "音樂頻道"
    kids_anime_keywords = ["卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼儿", "宝宝", "宝贝", "炫动", "酷",
        "炫酷", "卡通片", "动漫片", "动画片", "小公", "CARTOON", "ANIME", "ANIMATION", "KIDS", "睛彩青少", "青少"
        "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS", "TOON", "BOOMERANG", "尼克"]
    if any(k in s for k in kids_anime_keywords): return "少兒動漫"
    movie_keywords = [
       "至臻", "爱奇艺", "爆谷", "影", "HBO", "POPC", "邵氏", "娱乐", "经典", "戏", "剧",
        "MOVIE", "SERIES", "天映", "黑莧", "龙华", "片", "偶像", "影剧", "映画", "影迷",
        "新视觉", "好莱坞", "采昌", "美亚", "纬来", "ASTRO", "剧集", "电影", "影院",
        "剧场", "点播", "STAR", "SHORTS", "NETFLIX", "Prime", "Disney+", "Paramount+",
        "Peacock", "Max", "Showtime", "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime",
        "Hallmark", "华纳", "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
        "Marvel", "DCU", "Star Wars", "剧场版", "纪录片", "真人秀", "综艺", "真人实境",
        "DLIFE", "NECO", "The Cinema", "家庭剧场", "Homedrama", "Family Gekijo", "Entermei Tele"
    ]
    if any(k in s for k in movie_keywords): return "影視劇集"
    overseas_keywords = [
      "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理", "香港", "华文",
        "华艺", "环球", "生命", "镜", "澳", "台湾", "年代", "明珠", "唯心", "公视", "东森", "三立",
        "爱尔达", "NOW", "VIU", "HBO", "STAR", "星空", "纬来", "非凡", "中天", "无线", "寰宇", "GOOD",
        "ROCK", "华视", "台视", "中视", "民视", "TVBS", "八大", "龙祥", "靖天", "AXN", "KIX", "HOY",
        "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视", "大爱", "人间", "客家", "壹电视", "镜电视",
        "中视新闻", "民视新闻", "三立新闻", "东森新闻", "TVB News", "TVBS News", "SET News", "FTV News",
        "CTI", "CTS", "PTS", "NTV", "Fuji TV", "NHK", "TBS", "WOWOW", "Sky", "ESPN", "beIN", "DAZN",
        "Eleven Sports", "SPOTV NOW", "TrueVisions", "Astro", "Unifi TV", "HyppTV", "myTV SUPER", "Now TV",
        "Cable TV", "PCCW", "HKTV", "Viu", "Netflix", "Disney+",
        "TVBS", "TVBSG", "TVBSASIA", "TVBPLUS", "TVBJ1", "TVBD", "TVBASIANDRAMA", "TVB1", "TV9",
        "TTV", "TTV新闻", "TTVFINANCE", "TRANSTV", "TLC", "SURIA", "SUPERFREE", "SUNTV", "SUNEWS",
        "SUMUSIC", "SULIF", "SUKART", "SPOT2", "SPOT", "SONYTEN3", "SET新闻", "RTV", "ROCKACTION",
        "RIA", "QJ", "OKEY", "NOW", "NOW财经", "NOW新闻", "NHKWORLD", "NET", "MTLIVE", "METRTV",
        "MEDICIARTS", "MEDICARTS", "LIFETIME", "LIFETIM", "KPLUS", "KOMPASTV", "KMTV", "KBSWORLD",
        "INEWS", "INDOSIAR", "HUAHEEDAI", "HOY资讯", "HOYINFOTAINMENT", "HOY78", "HOY77", "HOY76",
        "HKS", "HITS", "HGT", "HB强档", "HB家庭", "GTVVARIETY", "GTVDRAMA", "GOOD福音2", "GOODTV福音",
        "GLOBALTREKKER", "FTV新闻", "FTVONE", "FTV", "FASHIONTV2", "EVE", "EUROSPOR", "EURONEWS",
        "EBCSUPERTV", "EBCFINANCIAL新闻", "DAZ1", "CTI新闻+", "CTITVVARIETY", "COLORSTAMIL",
        "CNN印尼", "CNBC", "CITRA", "CINEMAX", "CINEMAWORLD", "CHU", "CH8", "CH5", "BT", "BLTV",
        "BERNAMANEWS", "BBCWORLD", "BBCBEEBIES", "B4UMUSIC", "AXN", "AWESOME", "AWESOM", "AWANI",
        "ARENABOLA", "AOD", "ANIMAX", "ANIMALPLANET", "ANIMALPLANE", "ALJAZEERA", "AFN", "AF", "AEC",
        "8TV", "耀才财经", "中旺", "八度空间"
    ]
    if any(k in s for k in overseas_keywords): return "港澳台境外"
    return "其他頻道"

def check(line):
    try:
        name, url = [x.strip() for x in line.split(",", 1)]
        start = time.time()
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        headers = {'User-Agent': UA, 'Referer': domain or REFERER, 'Origin': domain}

        proxies = {'http':PROXY,'https':PROXY} if PROXY else None
        try:
            r = requests.head(url, headers=headers, timeout=3, allow_redirects=True, proxies=proxies)
            if r.status_code not in (200, 206, 301, 302):
                return {"status":"失效", "name":name, "url":url}
        except:
            try:
                r = requests.get(url, headers=headers, timeout=5, stream=True, proxies=proxies)
                if r.status_code != 200:
                    return {"status":"失效", "name":name, "url":url}
                r.close()
            except:
                return {"status":"失效", "name":name, "url":url}

        headers_str = '\r\n'.join(f'{k}: {v}' for k,v in headers.items()) + '\r\n\r\n'
        cmd = [
            'ffprobe', '-headers', headers_str, '-v', 'error',
            '-show_entries', 'format=duration',
            '-probesize', '1500000',
            '-analyzeduration', '4000000',
            '-timeout', '60000000',           # 60秒（微秒）
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
            url
        ]
        if PROXY: cmd.extend(['-http_proxy', PROXY])

        proc = subprocess.run(cmd, capture_output=True, timeout=70)  # 总超时70秒

        if proc.returncode == 0:
            return {"status":"有效", "name":name, "url":url, "lat":round(time.time()-start,2)}

        return {"status":"失效", "name":name, "url":url}

    except Exception as e:
        print(f"Error checking {name}: {e}")
        return {"status":"失效", "name":name, "url":url}

def parse_m3u(lines):
    parsed = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            attrs = re.findall(r'(\w+-\w+|\w+)="([^"]*)"', line)
            attr_dict = dict(attrs)
            if ',' in line:
                display_name = line.split(',', 1)[1].strip()
            else:
                display_name = ''
            if not display_name and 'tvg-name' in attr_dict:
                display_name = attr_dict['tvg-name']
            display_name = fix_mojibake(display_name)
            i += 1
            if i < len(lines):
                url_line = lines[i].strip()
                if not url_line.startswith('#') and url_line:
                    url = url_line
                    if display_name and url:
                        parsed.append(f"{display_name},{url}")
        elif line.startswith('#EXTM3U'):  # 忽略额外的 #EXTM3U 行，包括带属性的
            pass
        i += 1
    return parsed

def fetch_web_sources(url):
    try:
        proxies = {'http': PROXY, 'https': PROXY} if PROXY else None
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=10, proxies=proxies)
        if resp.status_code == 200:
            encodings = ['utf-8', 'gbk', 'big5']
            content = None
            for enc in encodings:
                try:
                    content = resp.content.decode(enc)
                    break
                except UnicodeDecodeError:
                    pass
            if content is None:
                content = resp.text  # fallback
            
            lines = content.splitlines()
            if any(l.strip().startswith('#EXTM3U') for l in lines):
                return parse_m3u(lines)
            else:
                return lines
        else:
            print(f"❌ 无法下载网页源: {url} (状态码: {resp.status_code})")
            return []
    except Exception as e:
        print(f"❌ 下载网页源失败: {url} - {e}")
        return []

def read_local_file():
    lines = []
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'big5']
    content = None
    for enc in encodings:
        try:
            with open(INPUT_FILE, 'r', encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            pass
        except Exception:
            continue
    if content is None:
        print(f"❌ 无法读取本地文件: {INPUT_FILE} (编码问题)")
        return []
    
    lines = content.splitlines()
    if any(l.strip().startswith('#EXTM3U') for l in lines):
        return parse_m3u(lines)
    else:
        return lines

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 输入文件不存在: {INPUT_FILE}")
        return

    seen_urls = set()
    lines_to_check = []

    local_lines = read_local_file()
    for l in local_lines:
        l = l.strip()
        if "," not in l or "://" not in l: continue
        parts = l.split(",", 1)
        if len(parts) != 2: continue
        raw_name = fix_mojibake(parts[0].strip())
        url = parts[1].strip()
        if url in seen_urls: continue
        seen_urls.add(url)
        cn = clean_name(raw_name)
        if cn:
            lines_to_check.append(f"{cn},{url}")

    if WEB_SOURCES:
        print(f"🚀 下载 {len(WEB_SOURCES)} 个网页源...")
        for url in WEB_SOURCES:
            for l in fetch_web_sources(url):
                l = l.strip()
                if "," not in l or "://" not in l: continue
                parts = l.split(",", 1)
                if len(parts) != 2: continue
                raw_name = fix_mojibake(parts[0].strip())
                url = parts[1].strip()
                if url in seen_urls: continue
                seen_urls.add(url)
                cn = clean_name(raw_name)
                if cn:
                    lines_to_check.append(f"{cn},{url}")

    random.shuffle(lines_to_check)
    total = len(lines_to_check)
    print(f"🚀 共 {total} 条待测源（URL 去重）")

    cat_map = {c:[] for c in ["4K/8K專區", "港澳台境外", "影視劇集", "央視頻道", "各地衛視", "體育賽事", "少兒動漫", "音樂頻道", "其他頻道"]}
    valid_count = 0
    other_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex, tqdm(total=total, desc="测活") as p:
        futures = [ex.submit(check, ln) for ln in lines_to_check]
        for f in as_completed(futures):
            r = f.result()
            p.update(1)
            if r and r["status"] == "有效":
                cat = get_category(r["name"])
                if cat in cat_map:
                    cat_map[cat].append(r)
                    valid_count += 1
                else:
                    other_count += 1
                    # print("未分类:", r["name"])  # 调试时打开

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"// 更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 有效源: {valid_count} | 未分类: {other_count}\n\n")
        for cat, items in cat_map.items():
            if not items: continue
            f.write(f"{cat},#genre#\n")
            grouped = {}
            for item in items:
                grouped.setdefault(item['name'], []).append(item)
            for name in sorted(grouped, key=lambda n: min(x['lat'] for x in grouped[n])):
                best = sorted(grouped[name], key=lambda x: x['lat'])[:MAX_LINKS_PER_NAME]
                for s in best:
                    f.write(f"{s['name']},{s['url']}\n")
            f.write("\n")

    print(f"✨ 任务完成！有效 {valid_count} 条，结果保存至 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()