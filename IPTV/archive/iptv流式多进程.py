# -*- coding: utf-8 -*-
import subprocess
import time
import os
import re
import random
import multiprocessing
from urllib.parse import urlparse
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from tqdm import tqdm

# ================= 配置区 =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "paste.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "live_ok.txt")

MAX_WORKERS = 40               # 每个进程内的线程数
TIMEOUT = 25
MAX_RETRIES = 1
MAX_LINKS_PER_NAME = 5
UA = 'Mozilla/5.0 (Linux; Android 10; TV Box) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36'
PROXY = None  

# 进程数（建议 4~8，根据 CPU 核心数调整）
PROCESSES = 4
# 每批处理条数（每批完成后刷新文件）
CHUNK_SIZE = 100

BLACKLIST = [
    "購物", "购物", "去購物", "備用", "直播間", "測試", "福利", "廣告", "下線", "加群",
    "提示", "下线", "教程", "聯繫", "联系", "用户", "会员", "使用", "推广", "进群",
    "否则", "免费", "切勿", "备用", "测试", "广告", "推广", "教程"
]

# ================= 工具函数 =================

def simplify(text):
    trans = str.maketrans(
        '衛視廣東體樂電影劇國際臺灣鳳凰翡翠亞畫愛爾達動兒龍粵華線衛星電視綜藝娛樂新聞財經購物備用測試福利廣告下線加群提示教程聯繫用戶會員使用推廣進群免費切勿音樂體育運動籃球賽馬跑馬電影影視劇影院動畫卡通兒童紀實探索發現紀錄百姓生活法制政法兵器國防旅遊健康養生動物科教教育',
        '卫视广东体乐电影剧国际台湾凤凰翡翠亚画爱尔达动儿龙粤华线卫星电视综艺娱乐新闻财经购物备用测试福利广告下线加群提示教程联系用户会员使用推广进群免费切勿音乐体育运动篮球赛马跑马电影影视剧影院动画卡通儿童纪实探索发现纪录百姓生活法制政法兵器国防旅游健康养生动物科教教育'
    )
    return text.translate(trans).upper()

def get_url_fingerprint(url):
    try:
        p = urlparse(url)
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        path = p.path
        query = p.query
        return f"{host}{port}{path}{query or ''}"
    except:
        return url

def clean_name(name: str) -> str:
    if not name: return ""
    
    name = re.sub(r'\[.*?\]|（.*?）|\(.*?\)|\{.*?\}|【.*?】|《.*?》', '', name)
    
    name = re.sub(r'(?i)CCTV\s*[-—_～•·:·\s]*(\d{1,2})(\+)?', r'CCTV\1\2', name)
    
    if not re.search(r'(?i)4K|8K|超高清', name):
        cctv_match = re.search(r'(?i)(CCTV\d{1,2}\+?)', name)
        if cctv_match:
            return cctv_match.group(1).upper()

    name = re.sub(r'(?i)[-_—～•·:·\s\u3000\u00A0\u200B\u200C\u200D\uFEFF\t\n\r]|HD|高清|超清|HDR|标清', '', name)
    
    name = re.sub(r'(?i)頻道|频道|直播|主線|台$', '', name)
    
    return name.strip()

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

    sport_keywords = ["体育", "运动", "足球", "棋", "篮球", "CCTV5", "五星体育", "咪视", "竞技", "SPORT", "SPOTV", "BALL", "跑马", "晴彩", "咪咕视频", "NBA", "英超", "11", "ELEVEN", "GOLF", "高尔夫", "网球", "賽馬"]
    if any(k in s for k in sport_keywords):
        return "體育賽事"

    music_keywords = ["音乐", "歌", "MTV", "CONCERT", "曲", "串烧", "周年", "演唱", "首", "点播", "CMUSIC", "KTV", "流行"]
    if any(k in s for k in music_keywords):
        return "音樂頻道"

    kids_anime_keywords = [
        "卡通", "动漫", "动画", "兒童", "少儿", "幼儿", "宝宝", "宝贝",
        "炫动", "酷", "炫酷", "卡通片", "动漫片", "动画片", "小公",
        "CARTOON", "ANIME", "ANIMATION", "KIDS", "CHILDREN", "TODDLER",
        "BABY", "NICK", "DISNEY", "CARTOONS", "TOON", "BOOMERANG"
    ]
    if any(k in s for k in kids_anime_keywords):
        return "少兒動漫"

    movie_keywords = ["至臻", "IQIYI", "爆谷", "影", "HBO", "POPC", "剧", "邵氏", "娱乐", "经典", "集", "戏", "MOVIE", "SERIES", "天映", "黑莓", "龙华", "片", "(C)", "偶像", "影剧", "映画", "影迷", "新视觉", "好莱坞", "采昌", "美亚", "纬来", "ASTRO", "爱奇艺",   "劇集", "電影", "影院", "劇場", "點播", "STAR", "SHORTS", "KIDS"]
    if any(k in s for k in movie_keywords):
        return "影視劇集"

    overseas_keywords = ["翡翠", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理", "香港", "面包", "华文", "地理", "华艺", "环球", "生命", "镜", "澳", "台湾", "年代", "明珠", "唯心", "公视", "东森", "三立", "爱尔达", "NOW", "VIU", "HBO", "STAR", "星空", "纬来", "非凡", "中天", "无线", "寰宇", "GOOD", "ROCK", "华视", "台视", "中视", "民视", "TVBS", "八大", "龙祥", "靖天", "AXN", "KIX", "HOY", "LOTUS", "蓮花"]
    if any(k in s for k in overseas_keywords):
        return "港澳台境外"

    return "其他頻道"

# ================= 测活单条逻辑 =================

def check_url(line):
    try:
        name, url = [x.strip() for x in line.split(",", 1)]
        ipv6 = "[IPv6]" if "[" in url and "]" in url else ""
        start_time = time.time()

        cmd = [
            'ffprobe',
            '-headers', f'User-Agent: {UA}\r\n',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-timeout', str(TIMEOUT * 1000000),
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            url
        ]

        for _ in range(MAX_RETRIES):
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT + 5)
                if proc.returncode == 0:
                    latency = round(time.time() - start_time, 2)
                    return {"status": "有效", "name": name + ipv6, "url": url, "lat": latency}
            except:
                pass
            time.sleep(0.5)

        return {"status": "失效", "name": name, "url": url}
    except:
        return None

# ================= 批处理任务 =================

def process_chunk_task(chunk):
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_url, ln): ln for ln in chunk}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
    return results

# ================= 主程序 =================

def main():
    if PROXY:
        os.environ['http_proxy'] = PROXY.get('http', '')
        os.environ['https_proxy'] = PROXY.get('https', '')

    if not os.path.exists(INPUT_FILE):
        print(f"❌ 输入文件不存在: {INPUT_FILE}")
        return

    # 1. 预处理读取 + 去重 + 清理名
    seen_fp = set()
    unique_lines = []
    for enc in ['utf-8-sig', 'utf-8', 'gbk']:
        try:
            with open(INPUT_FILE, "r", encoding=enc, errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if "," not in line or "://" not in line: continue
                    
                    parts = line.split(",", 1)
                    raw_name, url = parts[0].strip(), parts[1].strip()
                    
                    c_name = clean_name(raw_name)
                    if not c_name: continue
                    
                    fp = get_url_fingerprint(url)
                    if fp not in seen_fp:
                        seen_fp.add(fp)
                        unique_lines.append(f"{c_name},{url}")
            break
        except: continue

    random.shuffle(unique_lines)  # 打乱顺序，避免顺序相关限流
    total_count = len(unique_lines)
    print(f"✅ 数据就绪: {total_count} 条")

    # 2. 分批处理（流式保存）
    chunks = [unique_lines[i:i + CHUNK_SIZE] for i in range(0, total_count, CHUNK_SIZE)]
    
    # 用于存储分类结果（名字+URL）
    cat_results = {c: [] for c in ["4K/8K專區", "港澳台境外", "影視劇集", "央視頻道", "各地衛視", "體育賽事", "少兒動漫","音樂頻道", "其他頻道"]}
    name_counts = {}  # 每个纯名已写入多少条

    # 清空输出文件并写入开始标记
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("--- 测活开始 " + time.strftime("%Y-%m-%d %H:%M:%S") + " ---\n")

    print(f"🚀 启动流式检测模式 (进程: {PROCESSES} × 线程: {MAX_WORKERS})")

    valid_count = 0
    with ProcessPoolExecutor(max_workers=PROCESSES) as p_executor, \
         tqdm(total=total_count, desc="流式测活进度", unit="源") as pbar:

        p_futures = [p_executor.submit(process_chunk_task, chunk) for chunk in chunks]
        
        for pf in as_completed(p_futures):
            chunk_res_list = pf.result()
            
            # 提取有效源
            new_valids = [r for r in chunk_res_list if r["status"] == "有效"]
            if new_valids:
                valid_count += len(new_valids)
                for res in new_valids:
                    cat = get_category(res["name"])
                    if cat and cat in cat_results:
                        pure = res['name'].replace("[IPv6]", "")
                        count = name_counts.get(pure, 0)
                        if count < MAX_LINKS_PER_NAME:
                            cat_results[cat].append(f"{res['name']},{res['url']}")
                            name_counts[pure] = count + 1
                
                # 每批完成后，覆盖刷新文件（保持分组顺序）
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    f.write("--- 测活中 " + time.strftime("%Y-%m-%d %H:%M:%S") + f" --- 已测: {valid_count}/{total_count} ---\n")
                    for cat in ["4K/8K專區", "港澳台境外", "影視劇集", "央視頻道", "各地衛視", "體育賽事", "少兒動漫","音樂頻道", "其他頻道"]:
                        if cat in cat_results and cat_results[cat]:
                            f.write(f"{cat},#genre#\n")
                            for item in cat_results[cat]:
                                f.write(f"{item}\n")
                        f.write("\n")  # 分类间空行
            
            pbar.update(len(chunk_res_list))

    # 最终完成标记
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n--- 测活完成 {time.strftime('%Y-%m-%d %H:%M:%S')} --- 有效源: {valid_count} ---\n")

    print(f"\n✨ 检测圆满完成！有效源: {valid_count} | 最终结果: {OUTPUT_FILE}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()