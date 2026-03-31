#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV 影视仓 - 全自动1000+源获取器
自动循环迭代，爬虫+网页源+多轮检测，直到>=1000条可用源
"""
import os, re, random, time, requests, warnings, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from urllib.parse import urlparse
from datetime import datetime

warnings.filterwarnings('ignore')
os.chdir('C:/Users/Administrator/.qclaw/workspace/iptv_optimizer/output')

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'VLC/3.0.18 LibVLC/3.0.18 (LGPLv2.1+)',
    'Kodi/21.0 (Omega)',
    'TiviMate/4.7.0 (Android TV)',
    'Mozilla/5.0 (Linux; Android 13; TV Box) Chrome/120.0.0.0 Safari/537.36',
]

# 多源列表（按规模排序，大的放前面）
ALL_SOURCES = [
    # 最大聚合源 (iptv-org)
    ('iptv-org全球', 'https://iptv-org.github.io/iptv/index.m3u'),
    ('iptv-org中国', 'https://iptv-org.github.io/iptv/countries/cn.m3u'),
    ('iptv-org台湾', 'https://iptv-org.github.io/iptv/countries/tw.m3u'),
    ('iptv-org香港', 'https://iptv-org.github.io/iptv/countries/hk.m3u'),
    ('iptv-org澳门', 'https://iptv-org.github.io/iptv/countries/mo.m3u'),
    # 中国源
    ('CCTV合集', 'https://peterhchina.github.io/iptv/CNTV-V4.m3u'),
    ('饭太硬源', 'https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt'),
    ('Guovin源', 'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt'),
    ('范老师源', 'https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u'),
    ('小红包', 'https://live.zbds.top/tv/iptv4.m3u'),
    ('年新源', 'https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt'),
    ('大口源', 'https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u'),
    ('264788', 'https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt'),
    ('FGBLH港台', 'https://raw.githubusercontent.com/FGBLH/FG/refs/heads/main/%E6%B8%AF%E5%8F%B0%E5%A4%A7%E9%99%86'),
    ('judy源', 'https://raw.githubusercontent.com/judy-gotv/iptv/main/litv.m3u'),
    ('hacks香港', 'https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u'),
    ('hacks台湾', 'https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u'),
    ('hacks澳门', 'https://live.hacks.tools/tv/ipv4/categories/macau.m3u'),
    ('hacks电影', 'https://live.hacks.tools/tv/ipv4/categories/%E7%94%B5%E5%BD%B1%E9%A2%91%E9%81%93.m3u'),
    ('hacks中文', 'https://live.hacks.tools/iptv/languages/zho.m3u'),
    ('咪咕接口', 'https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt'),
    ('tv123', 'http://tv123.vvvv.ee/tv.m3u'),
    # 台湾香港
    ('台湾IPTV', 'https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8'),
    ('香港IPTV', 'https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8'),
    ('澳门IPTV', 'https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8'),
    ('Michael香港', 'https://raw.githubusercontent.com/MichaelJorky/Free-IPTV-M3U-Playlist/main/iptv-hongkong.m3u'),
    # 更多备用
    ('远走高飞', 'https://raw.githubusercontent.com/yuanzhouxia/zhwzczp/main/IPTV'),
    ('imDazui台港澳', 'https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u'),
    ('dsj10', 'https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt'),
    ('yuantailing', 'https://raw.githubusercontent.com/yuantailing/live/main/tv.m3u'),
    ('imDazui总', 'https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/iptv.m3u'),
    ('ZhangGaoyuan', 'https://raw.githubusercontent.com/zhanggaoyuan/AgileConfig/main/tv.m3u'),
    ('ChiShengChen', 'https://raw.githubusercontent.com/ChiShengChen/ChiShengChen.github.io/master/TV/IPTV.m3u'),
    # 东南亚
    ('sgb新加坡', 'https://iptv-org.github.io/iptv/countries/sg.m3u'),
    ('my马来西亚', 'https://iptv-org.github.io/iptv/countries/my.m3u'),
    ('th泰国', 'https://iptv-org.github.io/iptv/countries/th.m3u'),
    ('jp日本', 'https://iptv-org.github.io/iptv/countries/jp.m3u'),
    ('kr韩国', 'https://iptv-org.github.io/iptv/countries/kr.m3u'),
    # 美国
    ('us美国', 'https://iptv-org.github.io/iptv/countries/us.m3u'),
    ('uk英国', 'https://iptv-org.github.io/iptv/countries/gb.m3u'),
    ('de德国', 'https://iptv-org.github.io/iptv/countries/de.m3u'),
    ('fr法国', 'https://iptv-org.github.io/iptv/countries/fr.m3u'),
    # 其他
    ('global语言', 'https://iptv-org.github.io/iptv/languages/zho.m3u'),
    ('global娱乐', 'https://iptv-org.github.io/iptv/categories/entertainment.m3u'),
    ('global电影', 'https://iptv-org.github.io/iptv/categories/movies.m3u'),
    ('global体育', 'https://iptv-org.github.io/iptv/categories/sports.m3u'),
]

CATEGORIES = [
    ('4K專區', ['4K','8K','UHD','2160','HDR','杜比']),
    ('央視頻道', ['CCTV','中央','央视','CETV','中国教育']),
    ('衛視綜藝', ['卫视','湖南','浙江','江苏','东方','北京','广东','山东','四川']),
    ('新聞資訊', ['新闻','资讯','财经','CCTV13','凤凰资讯']),
    ('體育賽事', ['体育','足球','篮球','NBA','F1','奥运','英超','中超','CBA','斯诺克','电竞','咪咕']),
    ('少兒動漫', ['卡通','动漫','动画','少儿','儿童','KIDS','CARTOON','ANIME']),
    ('音樂頻道', ['音乐','MTV','KTV']),
    ('影視劇場', ['影视','电影','剧场','剧集','NETFLIX','HBO']),
    ('港澳台國外', ['TVB','凤凰','翡翠','香港','台湾','TVBS','BBC','CNN','NHK','ViuTV','Discovery','HBO','Star']),
    ('其他頻道', []),
]

BAD_DOMAINS = [
    'youku.com','iqiyi.com','qq.com','mgtv.com','bilibili.com',
    'douyin.com','kuaishou.com','tudou.com','pptv.com','le.com','sohu.com',
    'v.qq.com','wasu.cn','fun.tv','wasu.tv','migu.cn',
]
BAD_PATTERNS = ['购物','备用','测试','福利','广告','下线','加群','提示',
                 '推广','免费','无效','过期','失效','禁播','视频','点播','直播带货']

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print('[{}] {}'.format(ts, msg))

def fetch_m3u(url):
    try:
        r = requests.get(url, headers={'User-Agent': random.choice(UA_POOL)},
                       timeout=20, verify=False)
        r.close()
        if r.status_code != 200 or len(r.text) < 100:
            return []
        stripped = r.text.strip()[:300].lower()
        if '<!doctype html' in stripped or '<html' in stripped or '{"code"' in stripped:
            return []
        return r.text
    except:
        return None

def parse_m3u(text):
    entries = []
    lines = text.splitlines()
    name = None
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('#EXTINF:'):
            m = re.search(r'tvg-name="([^"]*)"', line)
            name = m.group(1) if m else None
            if not name:
                m2 = re.search(r',([^,\r\n]+)$', line)
                name = m2.group(1).strip() if m2 else None
        elif line.startswith('http'):
            entries.append((name or 'Unknown', line))
            name = None
        elif ',' in line and not line.startswith('#'):
            parts = line.split(',', 1)
            if len(parts) == 2 and parts[1].strip().startswith('http'):
                entries.append((parts[0].strip(), parts[1].strip()))
    return entries

def parse_plain(text):
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if ',' in line:
            parts = line.split(',', 1)
            if len(parts) == 2 and parts[1].strip().startswith('http'):
                entries.append((parts[0].strip(), parts[1].strip()))
    return entries

def clean_name(name):
    name = re.sub(r'[()\[\]{}]', '', name).strip()
    name = re.sub(r'[-_]+$', '', name)
    name = re.sub(r'^(HD|4K|8K|1080p|720p|360p|540p|高清|超清|标清|备用|线路)', '', name, flags=re.IGNORECASE)
    return name or 'Unknown'

def is_valid(url):
    try:
        p = urlparse(url)
        return p.scheme in ('http','https') and bool(p.netloc)
    except:
        return False

def filter_entry(name, url):
    if not is_valid(url): return False
    domain = urlparse(url).netloc.lower()
    if any(d in domain for d in BAD_DOMAINS): return False
    if domain.startswith(('127.','192.168.','10.','172.16.','172.17.',
                          '172.18.','172.19.','172.20.','172.21.','172.22.',
                          '172.23.','172.24.','172.25.','172.26.','172.27.',
                          '172.28.','172.29.','172.30.','172.31.','localhost')):
        return False
    if any(p in name for p in BAD_PATTERNS): return False
    return True

def check_stream(name, url, timeout=5):
    try:
        headers = {
            'User-Agent': random.choice(UA_POOL),
            'Range': 'bytes=0-1023',
        }
        r = requests.head(url, headers=headers, timeout=timeout,
                         allow_redirects=True, verify=False)
        r.close()
        if r.status_code not in (200, 206, 301, 302, 304):
            r = requests.get(url, headers=headers, timeout=timeout,
                           allow_redirects=True, verify=False, stream=True)
            if r.status_code not in (200, 206):
                return None
            r.close()
        return {'name': name, 'url': url}
    except:
        return None

def classify(name):
    nl = name.lower()
    for cat, kws in CATEGORIES:
        for kw in kws:
            if kw.lower() in nl:
                return cat
    return '其他頻道'

def merge_and_save(valid_list, round_num):
    """按频道合并，保留最优"""
    ch_map = defaultdict(list)
    for v in valid_list:
        ch_map[v['name']].append(v)

    result = []
    for name, items in ch_map.items():
        result.extend(items[:2])

    os.makedirs('.', exist_ok=True)

    # TXT
    with open('live_ok.txt', 'w', encoding='utf-8') as f:
        for v in result:
            f.write('{},{}\n'.format(v['name'], v['url']))

    # M3U
    m3u = ['#EXTM3U', '']
    for cat, _ in CATEGORIES:
        items = [v for v in result if classify(v['name']) == cat]
        if not items: continue
        m3u.append('# ===== {} ({}条) ====='.format(cat, len(items)))
        for v in items:
            safe_name = v['name'].replace('"', "'")
            m3u.append('#EXTINF:-1 tvg-name="{}",{}'.format(safe_name, safe_name))
            m3u.append(v['url'])
        m3u.append('')

    with open('live_ok.m3u', 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u))

    # 分类统计
    cat_stats = defaultdict(int)
    for v in result:
        cat_stats[classify(v['name'])] += 1

    log('--- 第{}轮结果: {}条 ---'.format(round_num, len(result)))
    for cat, cnt in sorted(cat_stats.items(), key=lambda x: -x[1]):
        log('  {}: {}'.format(cat, cnt))

    return result

def auto_check(entries, batch_start, batch_size, workers=60):
    """检测一批，返回有效结果"""
    batch = entries[batch_start:batch_start+batch_size]
    log('  检测批次: {}-{} / {}'.format(batch_start+1, min(batch_start+batch_size, len(entries)), len(entries)))

    valid = []
    lock_i = [0]

    def check_one(item):
        i = lock_i[0]
        lock_i[0] += 1
        if i % 100 == 0 and i > 0:
            log('    进度: {}/{}'.format(i, len(batch)))
        return check_stream(item[0], item[1], timeout=5)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(check_one, e) for e in batch]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                valid.append(r)

    return valid

def run():
    TARGET = 1000
    print('='*60)
    print('IPTV 全自动 1000+ 源获取器')
    print('目标: {}条 | 时间: {}'.format(TARGET, datetime.now().strftime('%Y-%m-%d %H:%M')))
    print('='*60)

    all_valid = []
    all_seen_urls = set()

    # === 阶段1: 拉取所有源 ===
    log('[阶段1] 拉取所有直播源列表...')
    all_entries = []
    for label, url in ALL_SOURCES:
        text = fetch_m3u(url)
        if text:
            if text.strip().startswith('#EXTM3U'):
                entries = parse_m3u(text)
            else:
                entries = parse_plain(text)
            all_entries.extend(entries)
            log('  + {} -> {}条'.format(label, len(entries)))
        else:
            log('  - {} -> 失败'.format(label))

    log('原始总数: {}条'.format(len(all_entries)))

    # === 阶段2: 去重清洗 ===
    log('[阶段2] 去重清洗...')
    cleaned = []
    seen_fp = set()
    for name, url in all_entries:
        if not filter_entry(name, url): continue
        fp = url.split('?')[0]
        if fp in seen_fp: continue
        seen_fp.add(fp)
        cleaned.append((clean_name(name), url))

    log('去重后: {}条'.format(len(cleaned)))

    # === 阶段3: 分轮检测 ===
    log('[阶段3] 分轮并行检测...')

    BATCH = 500
    ROUNDS = 15
    workers = 80

    for round_num in range(1, ROUNDS+1):
        start = (round_num - 1) * BATCH
        if start >= len(cleaned):
            log('所有批次检测完毕')
            break

        log('>>> 第{}轮检测 开始'.format(round_num))

        # 检测这一批
        batch_valid = auto_check(cleaned, start, BATCH, workers=workers)

        # 合并（去重已有）
        new_count = 0
        for v in batch_valid:
            if v['url'] not in all_seen_urls:
                all_seen_urls.add(v['url'])
                all_valid.append(v)
                new_count += 1

        log('  本轮新增: {}/{}条'.format(new_count, len(batch_valid)))
        log('  累计有效: {}条'.format(len(all_valid)))

        # 合并保存
        result = merge_and_save(all_valid, round_num)

        if len(result) >= TARGET:
            log('')
            log('='*60)
            log('CONGRATULATIONS! {}条 >= {}目标达成!'.format(len(result), TARGET))
            log('='*60)
            break

        # 每轮间隔，让网络喘口气
        if round_num < ROUNDS:
            wait = 3
            log('  等待{}秒后继续...'.format(wait))
            time.sleep(wait)

    # === 最终结果 ===
    print('')
    print('='*60)
    print('最终结果: {}条可用源'.format(len(all_valid)))
    print('='*60)

    cat_stats = defaultdict(int)
    for v in all_valid:
        cat_stats[classify(v['name'])] += 1
    for cat, cnt in sorted(cat_stats.items(), key=lambda x: -x[1]):
        print('  {}: {}'.format(cat, cnt))

    print('')
    print('输出文件:')
    print('  live_ok.txt ({})'.format(len(all_valid)))
    print('  live_ok.m3u')
    print('时间: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    return len(all_valid)

if __name__ == '__main__':
    run()
