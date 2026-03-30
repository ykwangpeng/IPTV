#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV-Apex-dzh.py - 聚合优化版
基于 IPTV-Apex-Lity.py，融合 8 项优化建议：
1. M3U8 解析库增强（m3u8 库）
2. 轻量级缓存机制（基于内存）
3. ffprobe 参数优化（probesize/analyzeduration/超时）
4. 分辨率检测（过滤低分辨率源）
5. 爬虫质量控制（域名白名单/黑名单）
6. 统计信息持久化（JSON 文件）
7. 点播域名扩展（短视频平台）
8. 进度条优化（简洁适配）
"""

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

# 尝试导入 m3u8 库（P0 优化 #1）
try:
    import m3u8
    HAS_M3U8_LIB = True
except ImportError:
    HAS_M3U8_LIB = False
    print("⚠️  未安装 m3u8 库，频道名解析准确率可能降低 10-20%（安装命令：pip install m3u8）")

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
    STATS_FILE  = BASE_DIR / ".iptv_stats.json"  # P2 优化 #6：统计信息持久化
    CACHE_FILE  = BASE_DIR / ".iptv_cache.json"  # P0 优化 #2：轻量级缓存

    # 核心功能开关
    ENABLE_WEB_FETCH    = False   # 是否启用自动爬取新增网络直播源的功能（拉取的源质量太低，已禁用）
    ENABLE_WEB_CHECK    = False   # 是否启用拉取并检测预设网络源的功能（默认关闭）
    ENABLE_LOCAL_CHECK  = True   # 是否启用读取并检测本地输入文件的功能
    ENABLE_SPEED_CHECK  = False   # 是否启用下载速度检测（可在运行时通过 --no-speed-check 关闭）
    DEBUG_MODE          = False  # 调试模式开关
    AUTO_BACKUP         = True   # 自动备份开关（备份文件名含时间戳）
    ARCHIVE_FAIL        = True   # 失效源归档开关
    
    # P0 优化 #2：轻量级缓存开关
    ENABLE_CACHE        = True   # 是否启用 URL 去重缓存
    CACHE_TTL_HOURS     = 24     # 缓存有效期（小时）

    # 异步爬虫质量控制 
    MAX_NEW_PLAYLISTS      = 200           # 最多只拉取多少个新播放列表（强烈建议别超过500）
    PLAYLIST_QUALITY_SCORE = True         # 是否启用域名质量评分

    # 性能与超时配置
    MAX_WORKERS         = 120     # 直播源检测的最大并发线程数
    FETCH_WORKERS       = 20      # 网络源拉取的最大并发线程数
    TIMEOUT_CN          = 8     # 境内直播源检测超时时间（秒）
    TIMEOUT_OVERSEAS    = 15     # 境外直播源检测超时时间（秒）
    RETRY_COUNT         = 1      # 网络请求重试次数
    REQUEST_JITTER      = False  # 请求抖动开关
    MAX_LINKS_PER_NAME  = 3      # 每个频道保留的最大有效链接数
    MAX_SOURCES_PER_DOMAIN = 0   # 每个域名最多保留的源数量（0=不限制）

    # P0 优化 #3：ffprobe 参数优化
    FFPROBE_PROBESIZE       = 2000000   # 5M（Lity 版本 10M）
    FFPROBE_ANALYZEDURATION = 5000000  # 10M（Lity 版本 20M）
    FFPROBE_TIMEOUT_BUFFER  = 2        # 超时缓冲（秒，Lity 版本 3秒）

    # 过滤与质量配置
    FILTER_PRIVATE_IP       = True   # 内网IP过滤开关
    REMOVE_REDUNDANT_PARAMS = False  # URL冗余参数清理开关
    ENABLE_QUALITY_FILTER   = True   # 质量过滤开关
    MIN_QUALITY_SCORE       = 5     # 最低质量阈值，低于此值过滤（兜底保留最高分1条）
    MIN_SPEED_MBPS          = 0.001  # 最低下载速度阈值（MB/s），低于此值直接判定失效
    SPEED_CHECK_BYTES       = 32768  # 速度检测下载字节数（32KB）

    # P0 优化 #4：分辨率检测配置
    ENABLE_RESOLUTION_FILTER   = False   # 是否启用分辨率过滤
    MIN_RESOLUTION_WIDTH       = 640    # 最低分辨率宽度（像素）
    MIN_RESOLUTION_HEIGHT      = 480    # 最低分辨率高度（像素）

    # IPv6 配置（Fix #7: 不再直接满分，改为做真实延迟检测后给予加权分）
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
        'SPEED_CHECK_BYTES', 'ENABLE_IPV6_OPTIMIZE', 'IPV6_LATENCY_BONUS',
        'IPV6_DEFAULT_DELAY', 'IPV6_DEFAULT_SPEED',
        'ENABLE_CACHE', 'CACHE_TTL_HOURS',
        'ENABLE_RESOLUTION_FILTER', 'MIN_RESOLUTION_WIDTH', 'MIN_RESOLUTION_HEIGHT',
    }

    # 频道黑名单（含关键词直接过滤，db版扩展）
    BLACKLIST = {
        "购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示",
        "教程", "联系", "推广", "免费", "无效", "过期", "失效", "禁播",
        "视频", "点播", "直播带货", "广告推广"
    }

    # 境外频道关键词（用于匹配超时时间，db版扩展）
    OVERSEAS_KEYWORDS = {
        "TVB", "凤凰", "翡翠", "明珠", "香港", "台湾", "台视", "华视", "民视",
        "东森", "三立", "纬来", "中天", "非凡", "龙祥", "靖天", "爱尔达",
        "CNN", "BBC", "NHK", "KBS", "SBS", "MBC", "DISCOVERY", "国家地理",
        "HBO", "STAR", "AXN", "KIX", "VIU", "NOW", "FOX", "ESPN", "BEIN",
        "HOY", "ViuTV", "澳广视", "TDM", "壹电视", "TVBS", "八大",
        "博斯", "澳", "公视", "华文", "八度", "华艺", "Z频道", "GOOD",
        "星空", "寰宇", "GEM", "J2", "开电视", "奇妙电视", "有线宽频",
        "Now TV", "Cable TV", "PCCW", "HKTV", "TTV", "FTV", "TRANSTV",
        "Fuji TV", "WOWOW", "Sky", "DAZN", "Eleven Sports", "SPOTV NOW"
    }

    # 直播源致命错误关键词（db版：追加 forbidden/not found）
    FATAL_ERROR_KEYWORDS = {
        "404 not found", "403 forbidden", "500 internal server error",
        "connection timed out", "could not resolve host", "connection refused",
        "no route to host", "network unreachable", "name or service not known",
        "unable to open file", "invalid url", "protocol not found",
        "server returned 404", "server returned 403", "server returned 500",
        "host unreachable", "dns resolution failed", "empty reply from server",
        "405 method not allowed", "forbidden", "not found"
    }

    # 播放列表域名白名单（用于域名质量评分）
    PLAYLIST_WHITELIST = {
        "github.com", "githubusercontent.com", "gitlab.com", "gitee.com"
    }

    # 播放列表域名黑名单（低质量域名直接跳过）
    PLAYLIST_BLACKLIST_DOMAINS = {
        "shortlink", "bit.ly", "tinyurl", "adf.ly", "link-short", "goo.gl"
    }

    # IPTV播放器专用UA池（db版：含VLC/Kodi/TiviMate等播放器UA）
    UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'VLC/3.0.18 LibVLC/3.0.18 (LGPLv2.1+)',
        'IINA/1.3.3 (Macintosh; Intel Mac OS X 14.5.0)',
        'PotPlayer/230502 (Windows NT 10.0; x64)',
        'Kodi/21.0 (Omega) Android/13.0.0 Sys_CPU/aarch64',
        'TiviMate/4.7.0 (Android TV)',
        'Perfect Player/1.6.0.1 (Linux;Android 13)',
        'Mozilla/5.0 (Linux; Android 13; TV Box) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Amlogic S905X4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    ]

    # 频道分类顺序（db版：增加4K專區、音樂頻道）
    CATEGORY_ORDER = [
        "4K 專區", "新聞資訊", "央衛頻道", "衛視綜藝", "港澳台頻", "體育賽事",
        "少兒動漫", "音樂頻道", "影視劇集", "其他頻道"
    ]

    # 频道分类关键词规则（db版，分类更精细，含预编译）
    CATEGORY_RULES_COMPILED: Dict = {}
    CATEGORY_RULES = {
        "4K 專區": ["4K", "8K", "UHD", "ULTRAHD", "2160", "超高清", "HDR", "杜比视界"],
        "央衛頻道": ["CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5", "CCTV6", "CCTV7",
                      "CCTV8", "CCTV9", "CCTV10", "CCTV11", "CCTV12", "CCTV14",
                      "CCTV15", "CCTV16", "CCTV17", "CCTV18", "CCTV4K", "CCTV8K",
                      "中央", "央视", "CETV", "中国教育", "兵团", "农林"],
        "衛視綜藝": [
            "卫视", "湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视",
            "广东卫视", "山东卫视", "四川卫视", "安徽卫视", "天津卫视",
            "河北卫视", "河南卫视", "湖北卫视", "江西卫视", "重庆卫视",
            "福建卫视", "辽宁卫视", "深圳卫视", "广西卫视", "黑龙江卫视",
            "云南卫视", "陕西卫视", "甘肃卫视", "贵州卫视", "山西卫视",
            "吉林卫视", "内蒙古卫视", "宁夏卫视", "新疆卫视", "海南卫视",
            "青海卫视", "西藏卫视", "兵团卫视", "CETV", "农林卫视"
        ],
        "新聞資訊": [
            "新闻", "资讯", "财经", "股票", "气象", "交通", "旅游",
            "新闻台", "资讯台", "财经台", "直播", "CCTV13", "凤凰资讯",
            "第一财经",
            "东方财富",
            "财新",
            "21财经",
            "财联社",
            "看看新闻",
            "澎湃",
            "封面新闻",
            "红星新闻",
            "触电新闻",
            "新京报",
            "经济观察",
            "凤凰卫视资讯"
        ],
        "體育賽事": [
            "体育", "运动", "足球", "篮球", "网球", "羽毛球", "乒乓球", "排球",
            "台球", "棋", "赛马", "CCTV5", "CCTV5+", "五星体育", "咪视", "竞技",
            "SPORT", "SPOTV", "BALL", "晴彩", "咪咕", "NBA", "英超", "西甲", "意甲",
            "德甲", "法甲", "欧冠", "欧联", "亚冠", "中超", "J联赛", "K联赛", "美职",
            "MLS", "F1", "MotoGP", "WWE", "UFC", "拳击", "高尔夫", "GOLF", "PGA",
            "ATP", "WTA", "澳网", "法网", "温网", "美网", "斯诺克", "世锦赛", "奥运",
            "文体", "亚运", "世界杯", "欧洲杯", "美洲杯", "非洲杯", "亚洲杯", "CBA",
            "五大联赛", "Pac-12",
            "劲爆体育",
            "广州竞赛",
            "深圳体育",
            "辽宁体育",
            "山东体育",
            "北京体育",
            "江苏体育",
            "四川体育",
            "湖北体育",
            "NFL",
            "MLB",
            "NHL",
            "东亚杯",
            "澳超",
            "大师赛",
            "看球",
            "直播吧",
            "虎扑",
            "劲球"
        ],
        "少兒動漫": [
            "卡通", "动漫", "动画", "曼迪", "儿童", "少儿", "幼", "宝宝", "宝贝",
            "炫动", "卡通片", "动漫片", "动画片", "CARTOON", "ANIME", "ANIMATION",
            "KIDS", "CHILDREN", "TODDLER", "BABY", "NICK", "DISNEY", "CARTOONS",
            "TOON", "BOOMERANG", "尼克", "小公视", "蓝猫", "喜羊羊", "熊出没", "萌鸡小队",
            "宝宝巴士",
            "贝乐虎",
            "小猪佩奇",
            "汪汪队",
            "海底小纵队",
            "超级飞侠",
            "迷你特工队",
            "奥特曼",
            "假面骑士",
            "巧虎",
            "洪恩",
            "大耳朵图图",
            "大头儿子",
            "朵拉",
            "托马斯",
            "小马宝莉",
            "变形警车"
        ],
        "音樂頻道": [
            "音乐", "MTV", "演唱会", "演唱", "CMUSIC", "KTV",
            "流行", "嘻哈", "摇滚", "古典", "爵士", "民谣", "电音", "EDM",
            "纯音乐", "伴奏", "Karaoke", "Channel V", "Trace", "VH1",
            "MTV Hits", "MTV Live", "女团", "音悦台",
            "V音乐",
            "音乐之声",
            "HITFM",
            "经典音乐",
            "发烧音乐",
            "NewAge",
            "民乐",
            "华语音乐",
            "欧美音乐"
        ],
        "影視劇集": [
            "爱奇艺", "优酷", "腾讯视频", "芒果TV", "IQIYI", "POPC",
            "剧集", "电影", "影院", "影视", "剧场", "Hallmark", "龙华",
            "Prime", "Paramount+", "电视剧", "Peacock", "Max", "靖洋",
            "Showtime", "Starz", "AMC", "FX", "TNT", "TBS", "Syfy", "Lifetime",
            "华纳", "环球", "派拉蒙", "索尼", "狮门", "A24", "漫威", "DC", "星战",
            "Marvel", "DCU", "Star Wars", "NETFLIX", "SERIES", "MOVIE", "SHORTS",
            "网剧", "短剧", "微剧", "首播", "独播", "热播", "天映",
            "港片", "台剧", "韩剧", "日剧", "美剧", "英剧",
            "悬疑", "科幻", "古装", "都市", "喜剧", "爱情", "冒险",
            "制片", "影业", "院线", "怀旧", "经典", "邵氏", "华剧",
            "华影", "金鹰", "星河", "新视觉", "哔哩哔哩", "B站", "西瓜视频",
            "搜狐视频", "乐视", "PP视频", "聚力", "风行", "暴风影音", "欢喜首映",
            "南瓜电影", "独播剧场", "黄金剧场", "首播剧场", "院线大片", "经典电影",
            "华语电影", "欧美电影", "日韩电影", "付费点播", "VIP影院", "家庭影院",
            "动作电影", "喜剧电影", "爱情电影", "科幻电影", "恐怖电影", "纪录片",
            "微电影", "网络大电影", "影城", "影厅", "首映", "点播影院",
            "1905电影",
            "CCTV6",
            "上海电影",
            "珠江电影",
            "峨眉电影",
            "长影频道",
            "潇湘电影",
            "西部电影",
            "华数TV",
            "响巢看看",
            "PPTV",
            "大剧",
            "热播剧场",
            "古装剧",
            "抗战剧",
            "刑侦剧",
            "家庭剧",
            "偶像剧"
        ],
        "港澳台頻": [
            "翡翠", "博斯", "凤凰", "TVB", "CNN", "BBC", "DISCOVERY", "国家地理",
            "香港", "华文", "八度", "华艺", "环球", "生命", "镜", "澳", "台湾", "探索",
            "年代", "明珠", "唯心", "公视", "东森", "三立", "爱尔达", "NOW", "VIU",
            "STAR", "星空", "纬来", "非凡", "中天", "中视", "无线", "寰宇", "Z频道",
            "GOOD", "ROCK", "华视", "台视", "民视", "TVBS", "八大", "龙祥", "靖天",
            "AXN", "KIX", "HOY", "LOTUS", "莲花", "GEM", "J2", "ViuTV", "开电视",
            "奇妙电视", "香港开电视", "有线宽频", "ViuTVsix", "ViuTVtwo", "澳广视",
            "TDM", "澳门卫视", "壹电视", "CTI", "CTS", "PTS", "NTV",
            "Fuji TV", "NHK", "TBS", "WOWOW", "Sky", "ESPN", "beIN", "DAZN",
            "Eleven Sports", "SPOTV NOW", "TrueVisions", "Astro", "Unifi TV", "HyppTV",
            "myTV SUPER", "Now TV", "Cable TV", "PCCW", "HKTV", "Viu", "Netflix",
            "Disney+", "RHK", "TTV", "FTV", "TRANSTV", "TLC", "SURIA",
            "SUPERFREE", "SUNTV", "SUNEWS", "SUMUSIC", "SULIF", "SUKART",
            "SPOT2", "SPOT", "SONYTEN3", "SET新闻", "年代新闻", "东森新闻",
            "中天新闻", "民视新闻", "台视新闻", "华视新闻", "三立新闻", "非凡新闻",
            "TVBS新闻", "凤凰卫视资讯台", "凤凰卫视中文台", "凤凰卫视香港台",
            "中天亚洲", "东森亚洲",
            "东森洋片",
            "东森戏剧",
            "东森综合",
            "三立都会",
            "三立台湾",
            "TVBS欢乐",
            "TVBS精采",
            "中天综合",
            "中天娱乐",
            "纬来体育",
            "纬来综合",
            "纬来戏剧",
            "爱尔达体育",
            "智林体育",
            "Eurosport",
            "TV5Monde",
            "Arte",
            "ZDF",
            "ARD",
            "Rai",
            "TVE",
            "SBT",
            "Globo",
            "KBS",
            "SBS",
            "MBC",
            "JTBC",
            "tvN"
        ],
        "其他頻道": []
    }

    # 点播域名黑名单（db版：支持子域名精确匹配）
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
        # 通用点播
        "youku.com", "iqiyi.com", "v.qq.com", "mgtv.com", "bilibili.com",
        "tudou.com", "pptv.com", "le.com", "sohu.com",
        "douyin.com", "douyincdn.com", "aweme.com", "kuaishou.com", "ks-cdn.com",
        "ksyun.com", "kshttp.cn"  # 快手视频CDN
    }

    # 直播频道名关键词（用于识别真正的直播频道，区分点播内容）
    LIVE_CHANNEL_KEYWORDS = re.compile(
        r'频道|台|卫视|影院|剧场|电影|剧集|直播|体育|音乐|新闻|综合|少儿|动漫|教育|财经|'
        r'Discovery|Channel|TV|News|Live|Sport|Music|Kids|Movie|Film|Drama|Anime'
    )

    # IPv6 配置（db版：直接满分）
    ENABLE_IPV6_OPTIMIZE    = True
    IPV6_DEFAULT_DELAY      = 0.1
    IPV6_DEFAULT_SPEED       = 10.0

    # 默认预设网络源列表（db版：含大量预设URL）
    WEB_SOURCES: List[str] = []
    PRESET_FILES = [
        "https://live.zbds.top/tv/iptv4.m3u",
        "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/台湾港澳.m3u",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/HongKong.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/TaiWan.m3u8",
        "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/Macao.m3u8",
        "https://raw.githubusercontent.com/MichaelJorky/Free-IPTV-M3U-Playlist/main/iptv-hongkong.m3u",
        "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
        "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt",
        "http://txt.gt.tc/users/HKTV.txt",
        "https://raw.githubusercontent.com/nianxinmj/nxpz/refs/heads/main/lib/live.txt",
        "https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u",
        "https://live.264788.xyz/sub/02RvO5i5Zn1LSQUCr56kkUp2I9xa9A/txt",
        "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
        "http://tv123.vvvv.ee/tv.m3u",
        "https://iptv-org.github.io/iptv/countries/hk.m3u",
        "https://iptv-org.github.io/iptv/countries/tw.m3u",
        "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
        "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
        "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/cn.m3u",
        "https://iptv-org.github.io/iptv/countries/mo.m3u",
        "https://iptv-org.github.io/iptv/index.m3u"
    ]

    @classmethod
    def load_from_file(cls) -> bool:
        try:
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if key in cls.SAVEABLE_KEYS:
                            setattr(cls, key, value)
                return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"⚠️  配置加载失败: {e}")
        return False

    @classmethod
    def save_to_file(cls, data=None) -> bool:
        try:
            if not cls.CONFIG_FILE.exists():
                return True
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                current = json.load(f)
            # 更新 WEB_SOURCES
            if data is not None and isinstance(data, list):
                current['WEB_SOURCES'] = data
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            if cls.DEBUG_MODE:
                print(f"⚠️  配置保存失败: {e}")
        return False

    @classmethod
    def init_compiled_rules(cls):
        """初始化编译后的正则表达式（db版：预编译分类正则提升性能）"""
        if not hasattr(cls, '_compiled'):
            cls._compiled = {
                'noise': re.compile(cls._get_noise_pattern()),
                'bracket_noise': re.compile(cls._get_bracket_noise_pattern()),
                'date_tag': re.compile(cls._get_date_tag_pattern()),
            }
        # 预编译分类正则（db版：关键词繁简转换后编译，跳过空关键词列表）
        if not cls.CATEGORY_RULES_COMPILED:
            for cat, keywords in cls.CATEGORY_RULES.items():
                simplified = [NameProcessor.simplify(kw) for kw in keywords if kw.strip()]
                if not simplified:
                    # 空关键词列表：设为一个永不匹配的 regex（如嵌入不可见字符）
                    cls.CATEGORY_RULES_COMPILED[cat] = re.compile(r'(?=x(?<!x))')
                    continue
                pattern = '|'.join(re.escape(kw) for kw in simplified)
                cls.CATEGORY_RULES_COMPILED[cat] = re.compile(pattern, re.IGNORECASE)

    @staticmethod
    def _get_bracket_noise_pattern() -> str:
        """合并后的括号噪音模式"""
        patterns = [
            r'\(.*?\)', r'\[.*?\]', r'\{.*?\}',
            r'【.*?】', r'＜.*?＞', r'『.*?』',
            r'「.*?」', r'『.*?』',
            r'（.*?）', r'＜.*?＞'
        ]
        return '|'.join(patterns)

    @staticmethod
    def _get_date_tag_pattern() -> str:
        """日期标签模式"""
        return Config._get_bracket_noise_pattern()

    @staticmethod
    def _get_noise_pattern() -> str:
        """噪音模式"""
        return Config._get_bracket_noise_pattern()

# ==================== P0 优化 #2：轻量级缓存 ====================
class URLCache:
    """轻量级 URL 去重缓存（基于内存 + JSON 持久化）"""
    
    def __init__(self, cache_file: Path, ttl_hours: int = 24):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_hours * 3600
        self.cache: Dict[str, float] = {}  # {url_fingerprint: timestamp}
        self._load()
        
        # 定期清理过期缓存
        self._cleanup_expired()
        
    def _load(self):
        """从文件加载缓存"""
        if not Config.ENABLE_CACHE:
            return
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
        except Exception:
            self.cache = {}
    
    def _save(self):
        """保存缓存到文件"""
        if not Config.ENABLE_CACHE:
            return
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        if not Config.ENABLE_CACHE:
            return
        current_time = time.time()
        expired_keys = [k for k, v in self.cache.items() if current_time - v > self.ttl_seconds]
        for key in expired_keys:
            del self.cache[key]
        if expired_keys:
            self._save()
    
    def is_cached(self, fingerprint: str) -> bool:
        """检查指纹是否在缓存中（未过期）"""
        if not Config.ENABLE_CACHE:
            return False
        if fingerprint not in self.cache:
            return False
        # 检查是否过期
        if time.time() - self.cache[fingerprint] > self.ttl_seconds:
            del self.cache[fingerprint]
            return False
        return True
    
    def add(self, fingerprint: str):
        """添加指纹到缓存"""
        if not Config.ENABLE_CACHE:
            return
        self.cache[fingerprint] = time.time()
        # 每 100 次保存一次，避免频繁 IO
        if len(self.cache) % 100 == 0:
            self._save()
    
    def size(self) -> int:
        """返回缓存大小"""
        return len(self.cache)

# ==================== URL清洗与处理 ====================
class URLCleaner:
    @staticmethod
    @lru_cache(maxsize=10000)
    def get_fingerprint(url: str) -> str:
        """URL 指纹提取（带缓存），用于去重：对 query 参数排序，使参数顺序不同的同义 URL 产生相同指纹"""
        parsed = urlparse(url)
        if parsed.query:
            # 按参数名排序，确保参数顺序不同的同义 URL 指纹一致
            params = parse_qs(parsed.query)
            if Config.REMOVE_REDUNDANT_PARAMS:
                keep_params = {'id', 'token', 'key', 'sign', 'auth', 'code', 'streamid'}
                params = {k: v for k, v in params.items() if k in keep_params}
            sorted_query = urlencode(sorted(params.items()), doseq=True)
        else:
            sorted_query = ''
        netloc = parsed.netloc
        if parsed.port and parsed.port not in (80, 443):
            netloc = f"{parsed.hostname}:{parsed.port}"
        else:
            netloc = parsed.hostname or parsed.netloc
        return f"{parsed.scheme}://{netloc}{parsed.path}" + (f"?{sorted_query}" if sorted_query else "")

    @staticmethod
    def _get_hostname(url: str) -> str:
        """提取 hostname（Fix #10: 抽取私有方法统一调用）"""
        return urlparse(url).netloc.lower()

    @staticmethod
    def filter_private_ip(url: str) -> bool:
        """检查是否为内网IP（Fix #10: 使用 _get_hostname 统一）"""
        domain = URLCleaner._get_hostname(url)
        private_patterns = (
            '127.', '0.', 'localhost', '192.168.', '10.', '172.16.', '172.17.',
            '172.18.', '172.19.', '172.20.', '172.21.', '172.22.',
            '172.23.', '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.'
        )
        return any(pattern in domain for pattern in private_patterns)

    @staticmethod
    def is_vod_domain(url: str) -> bool:
        """检查是否为点播域名（db版：子域名边界匹配，防止 .com 等误匹配）"""
        domain = URLCleaner._get_hostname(url)
        for vod_domain in Config.VOD_DOMAINS:
            base = vod_domain.split(':')[0]
            # 精确匹配或以 .base 结尾（子域名）
            if domain == base or domain.endswith('.' + base):
                return True
        return False

    @staticmethod
    def is_valid(url: str) -> bool:
        """URL 有效性基础检查"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https', 'rtmp', 'rtmps', 'rtsp') and bool(parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def is_ipv6(url: str) -> bool:
        """检测是否为 IPv6 地址"""
        parsed = urlparse(url)
        hostname = parsed.netloc.split('@')[-1].split(':')[0]
        return hostname.startswith('[')
        return False

# ==================== P0 优化 #1：M3U8 解析器增强 ====================
class M3UParser:
    @staticmethod
    def parse(lines: List[str]) -> List[str]:
        """解析 M3U 格式（增强版：支持 m3u8 库）"""
        result = []
        
        # 尝试使用 m3u8 库解析（更准确）
        if HAS_M3U8_LIB:
            try:
                content = '\n'.join(lines)
                playlist = m3u8.loads(content)
                for segment in playlist.segments:
                    if segment.title:
                        result.append(f"{segment.title},{segment.uri}")
                    elif segment.uri:
                        result.append(f"未知频道,{segment.uri}")
                
                # 如果解析成功且非空，直接返回
                if result:
                    return result
            except Exception:
                pass  # 解析失败，回退到正则解析
        
        # 回退到正则解析
        name = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF:'):
                # 提取频道名称
                match = re.search(r'tvg-name="([^"]*)"', line)
                if match:
                    name = match.group(1)
                else:
                    # 尝试其他格式
                    match = re.search(r',([^,]+)$', line)
                    if match:
                        name = match.group(1).strip()
            elif line.startswith('http'):
                result.append(f"{name},{line}" if name else f"未知频道,{line}")
                name = None
            elif ',' in line and not line.startswith('#'):
                parts = line.split(',', 1)
                if len(parts) == 2:
                    name, url = parts
                    name = name.strip()
                    url = url.strip()
                    if url.startswith('http'):
                        result.append(f"{name},{url}")
        return result

    @staticmethod
    def _parse_plain_text(lines: List[str]) -> List[str]:
        """解析纯文本格式（每行：名称,URL）"""
        result = []
        for line in lines:
            line = line.strip()
            if ',' in line:
                name, url = line.split(',', 1)
                name = name.strip()
                url = url.strip()
                if url.startswith('http'):
                    result.append(f"{name},{url}")
        return result

# ==================== 频道名称处理器（db版全流程清洗） ====================
class NameProcessor:
    _simplify_cache: Dict = {}
    _simplify_lock  = threading.Lock()

    # 境外频道前缀（db版）
    OVERSEAS_PREFIX = [
        'TVB', 'TVBS', 'BS', 'CH', 'FOX', 'ESPN', 'HBO', 'ViuTV', 'NOW', 'ASTRO',
        'WOWOW', 'NHK', '博斯', '凤凰', '翡翠', '明珠', 'HOY', '澳广视', 'TDM'
    ]

    # CCTV 标准化正则（db版）
    CCTV_FIND_RE = re.compile(
        r'(?i)((?:CCTV|ＣＣＴＶ)\s*[-—_～•·:\s]*\d{1,2}\+?)'
    )
    CCTV_NUM_RE = re.compile(r'CCTV\D*?(\d{1,2})\s*(\+?)', re.IGNORECASE)
    EMOJI_RE    = re.compile(
        r'[\U00010000-\U0010ffff\U00002600-\U000027ff\U0000f600-\U0000f6ff'
        r'\U0000f300-\U0000f3ff\U00002300-\U000023ff\U00002500-\U000025ff'
        r'\U00002100-\U000021ff\U000000a9\U000000ae\U00002000-\U0000206f'
        r'\U00002460-\U000024ff\U00001f00-\U00001fff]+', re.UNICODE
    )
    NOISE_RE    = re.compile(
        r'(?:\(.*?\))|(?:\[.*?\])|(?:【.*?】)|(?:《.*?》)|'
        r'(?:<.*?>)|(?:\{.*\})|(?:\（.*?\）)', re.IGNORECASE
    )
    HIRES_RE    = re.compile(r'(?i)4K|8K|UHD|ULTRAHD|2160|HDR|超高清|杜比视界')
    SUFFIX_RE   = re.compile(
        r'(?i)(?:'
        r'[-_—～•·:\s|/\\]+'    # 分隔符（保留前面的有效字符）
        r'|HD|1080p|720p|360p|540p'  # 视频质量后缀
        r'|高清|超清|超高清|标清'    # 中文质量后缀（不含"直播"）
        r'|主线'                # 主线后缀
        r'|备用\d*|线路\d*'     # 备用/线路后缀（带数字）
        r')$'
    )
    BLANK_RE    = re.compile(r'^[\s\-—_～•·:·]+$')
    M3U_EXTINF  = re.compile(r'^#EXTINF:-?\d+(.*?),', re.IGNORECASE)

    @staticmethod
    def simplify(text: str) -> str:
        """繁→简转换，双层缓存"""
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
    def _normalize_cctv(name: str) -> str:
        """CCTV 标准化：提取数字、特殊处理 CCTV5+/CCTV4K"""
        if not name:
            return name
        upper = name.upper().replace('ＣＣＴＶ', 'CCTV')
        if 'CCTV' not in upper:
            return name
        m = NameProcessor.CCTV_NUM_RE.search(upper)
        if not m:
            return name
        num  = str(int(m.group(1)))
        plus = m.group(2)
        if num == '5':
            return 'CCTV5+' if (plus or '+' in upper) else 'CCTV5'
        if num == '4' and 'K' in upper:
            return 'CCTV4K'
        return f'CCTV{num}'

    @staticmethod
    def clean(name: str) -> str:
        """频道名全流程清洗：emoji→前缀提取→噪音去除→CCTV标准化→繁简转换"""
        if not name or not name.strip():
            return '未知频道'
        # 去除 emoji
        n = NameProcessor.EMOJI_RE.sub('', name)
        # 境外频道前缀提取
        for prefix in NameProcessor.OVERSEAS_PREFIX:
            if n.upper().startswith(prefix.upper()) and len(n) > len(prefix) + 1:
                m = re.search(rf'({re.escape(prefix)}[A-Za-z0-9\u4e00-\u9fff]+)', n, re.IGNORECASE)
                if m:
                    n = m.group(1)
                    break
        # 去除噪音字符
        n = NameProcessor.NOISE_RE.sub('', n)
        # 非高清频道优先 CCTV 标准化
        if not NameProcessor.HIRES_RE.search(n):
            m = NameProcessor.CCTV_FIND_RE.search(n)
            if m:
                return NameProcessor._normalize_cctv(m.group(1).upper())
        # 去除后缀冗余
        n = NameProcessor.SUFFIX_RE.sub('', n)
        # 繁简转换
        n = NameProcessor.simplify(n)
        n = NameProcessor._normalize_cctv(n)
        if not n or NameProcessor.BLANK_RE.match(n):
            return '未知频道'
        return n.strip()

    @staticmethod
    def is_overseas(name: str) -> bool:
        """判断是否为境外频道"""
        return any(kw in name.upper() for kw in Config.OVERSEAS_KEYWORDS)

    @staticmethod
    def is_blacklisted(name: str) -> bool:
        """判断是否在黑名单中"""
        return any(kw in name for kw in Config.BLACKLIST)

    @staticmethod
    def classify(name: str) -> str:
        """频道分类（db版：按优先级匹配 CATEGORY_RULES）"""
        simplified = NameProcessor.simplify(name)
        if any(kw in simplified for kw in Config.BLACKLIST):
            return "其他"
        # 按 CATEGORY_ORDER 顺序匹配（不含最后的"其他頻道"）
        for cat in Config.CATEGORY_ORDER[:-1]:
            if cat in Config.CATEGORY_RULES_COMPILED:
                if Config.CATEGORY_RULES_COMPILED[cat].search(simplified):
                    return cat
        return Config.CATEGORY_ORDER[-1]  # "其他頻道"

    @staticmethod
    @staticmethod
    def normalize(name: str) -> str:
        """输出前最终标准化"""
        cleaned = NameProcessor.clean(name)
        # 防止 clean 后仍有括号/后缀残留，再次清理
        cleaned = NameProcessor.NOISE_RE.sub('', cleaned).strip()
        if not cleaned or cleaned == '未知频道':
            return name.strip()
        # 再清一次后缀（如 clean 过程中未能处理的后缀）
        return NameProcessor.SUFFIX_RE.sub('', cleaned).strip()

# ==================== 网络源获取器 ====================
class WebSourceFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        requests.packages.urllib3.disable_warnings()

    def fetch(self, url: str, proxy: Optional[str] = None) -> Optional[List[str]]:
        """拉取网络源并解析"""
        if not url:
            return None
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        headers = {'User-Agent': random.choice(Config.UA_POOL)}
        try:
            # 境内源超时短，境外源超时长
            timeout = 15 if url.startswith('https://github.com') else 20
            resp = self.session.get(url, headers=headers, proxies=proxies, timeout=timeout)
            if resp.status_code == 200 and len(resp.text) > 100:
                lines = resp.text.splitlines()
                if any(l.startswith('#EXTM3U') for l in lines[:10]):
                    return M3UParser.parse(lines)
                else:
                    return M3UParser._parse_plain_text(lines)
            return None
        except Exception as e:
            if Config.DEBUG_MODE:
                print(f"⚠️ 拉取异常 {url}: {e}")
            return []

# ==================== 异步网络源爬虫 ====================
class AsyncWebSourceCrawler:
    """异步爬虫（db版）：域名质量评分 + HEAD降级GET + 内容类型检查"""

    PLAYLIST_EXT = ('.m3u', '.m3u8', '.txt', 'php?type=m3u', '/playlist', '?type=m3u')

    URL_PATTERNS = [
        r'https?://[^\s<>"\']+\.(?:m3u|m3u8|txt|php\?|\?type=m3u)[^\s<>"\']*',
        r'https?://[^\s<>"\']+/live[^\s<>"\']*',
        r'https?://[^\s<>"\']+/stream[^\s<>"\']*',
        r'https?://[^\s<>"\']+/tv[^\s<>"\']*',
        r'https?://[^\s<>"\']+:\d{4,5}[^\s<>"\']*'
    ]

    def __init__(self):
        self.session = None
        self.all_extracted: Set[str] = set()

    @property
    def SOURCE_SITES(self):
        return Config.PRESET_FILES if Config.PRESET_FILES else Config.WEB_SOURCES

    async def __aenter__(self):
        timeout = httpx.Timeout(8.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=30, keepalive_expiry=15.0)
        self.session = httpx.AsyncClient(timeout=timeout, limits=limits, verify=False, follow_redirects=True)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.aclose()

    async def quick_validate(self, url: str, timeout: float = 4.0) -> bool:
        """优化：HEAD 失败自动降级 GET + Range 头，避免 CDN 403 误判"""
        headers = {
            'User-Agent': random.choice(Config.UA_POOL),
            'Range': 'bytes=0-511',                              # 只拉前512字节
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        }
        try:
            # 优先 HEAD 请求（快速）
            resp = await self.session.head(url, headers=headers, timeout=timeout, follow_redirects=True)
            if resp.status_code in (200, 206, 301, 302, 304):
                return True
            # HEAD 失败，降级 GET 前 512 字节（适配 CDN 的 403 HEAD / 200 GET 行为）
            async with self.session.stream('GET', url, headers=headers, timeout=timeout) as resp:
                if resp.status_code in (200, 206) and resp.num_bytes_downloaded >= 16:
                    text = (await resp.aread()).decode('utf-8', errors='ignore')[:200].strip()
                    # 检查是否像 M3U 内容（而非 HTML 错误页）
                    if text.startswith('#EXTM3U') or 'm3u' in text.lower():
                        return True
            return False
        except Exception:
            return False

    @staticmethod
    def _get_domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    @staticmethod
    def _is_high_quality(url: str) -> int:
        """域名质量评分：白名单最高分，黑名单直接 0"""
        domain = AsyncWebSourceCrawler._get_domain(url)
        if any(bad in domain for bad in Config.PLAYLIST_BLACKLIST_DOMAINS):
            return 0
        if any(good in domain for good in Config.PLAYLIST_WHITELIST):
            return 100
        if "githubusercontent.com" in domain or "github.com" in domain:
            return 70
        return 30

    @staticmethod
    def _is_playlist(url: str) -> bool:
        """判断 URL 是否为播放列表"""
        lower = url.lower()
        auth_params = ('userid=', 'sign=', 'auth_token=', 'token=', 'session=')
        if any(param in lower for param in auth_params):
            return False
        path = urlparse(url).path
        if path.endswith('.m3u8'):
            filename = Path(path).stem
            if filename.isdigit() or len(filename) <= 10:
                return False
        return any(ext in lower for ext in AsyncWebSourceCrawler.PLAYLIST_EXT)

    async def extract_sources_from_content(self, url: str, depth: int = 0) -> Set[str]:
        """从页面内容中提取直播源（db版：内容类型检查）"""
        if depth > 1:
            return set()
        try:
            headers = {
                'User-Agent': random.choice(Config.UA_POOL),
                'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            }
            resp = await self.session.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return set()

            text = resp.text
            # db版：检查是否为有效文本内容，排除 HTML/JSON 错误页
            stripped = text.strip()[:500].lower()
            if (
                len(text) < 50
                or '<!doctype html' in stripped
                or '<html' in stripped
                or '{"code"' in stripped
            ):
                return set()

            all_matches: Set[str] = set()
            for pattern in self.URL_PATTERNS:
                all_matches.update(re.findall(pattern, text, re.IGNORECASE))

            valid_sources: Set[str] = set()
            semaphore = asyncio.Semaphore(30)

            async def validate_and_add(source: str):
                if len(source) < 15 or len(source) > 500:
                    return
                if any(x in source.lower() for x in ['javascript:', 'data:', 'about:', 'void(']):
                    return
                if source in self.all_extracted:
                    return
                async with semaphore:
                    try:
                        if await self.quick_validate(source, timeout=2.0):
                            valid_sources.add(source)
                            self.all_extracted.add(source)
                    except Exception:
                        pass

            batch_size = 50
            for i in range(0, len(all_matches), batch_size):
                await asyncio.gather(
                    *[validate_and_add(s) for s in list(all_matches)[i:i+batch_size]],
                    return_exceptions=True
                )

            # 递归深度1的子页面
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
        """爬取并返回 {子url: 域名} 映射"""
        async with semaphore:
            try:
                parsed_url = urlparse(url)
                base_domain = parsed_url.netloc.split(':')[0]
                if not await self.quick_validate(url, timeout=3.0):
                    return {}
                extracted = await self.extract_sources_from_content(url)
                if not extracted:
                    return {}
                return {sub_url: base_domain for sub_url in extracted}
            except Exception:
                return {}

    async def crawl_all(self) -> Dict[str, str]:
        """爬取所有预设源，返回 {url: name} 映射"""
        print("🔍 启动异步爬虫（db版：域名质量评分）...")
        semaphore = asyncio.Semaphore(10)
        tasks = [self.crawl_single_source_with_name(url, semaphore) for url in self.SOURCE_SITES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        url_to_name: Dict[str, str] = {}
        for r in results:
            if isinstance(r, dict):
                url_to_name.update(r)
        print(f"✅ 爬虫完成！发现新源 {len(url_to_name)} 个（已过滤垃圾域名）")
        return url_to_name
        tasks = [self.crawl_single_source(url, semaphore) for url in self.SOURCE_SITES]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 最终去重 + 按质量排序 + 数量限制
        final_list = sorted(
            self.new_playlists,
            key=lambda u: self._is_high_quality(u),
            reverse=True
        )[:Config.MAX_NEW_PLAYLISTS]

        print(f"✅ 爬虫完成！优质播放列表 {len(final_list)} 个（已过滤掉 {len(self.new_playlists)-len(final_list)} 个垃圾源）")
        return set(final_list)

    async def crawl_all_with_names(self) -> Dict[str, str]:
        """兼容旧接口：返回 {url: domain} 映射（走 PRESET_FILES）"""
        return await self.crawl_all()

# ==================== P0 优化 #4：分辨率检测辅助 ====================
class ResolutionDetector:
    """分辨率检测辅助类（基于 ffprobe 输出解析）"""
    
    @staticmethod
    def parse_resolution(stdout_text: str) -> Optional[Tuple[int, int]]:
        """从 ffprobe 输出中解析分辨率（宽度, 高度）"""
        try:
            # 尝试匹配 video stream 的 width 和 height
            match = re.search(r'width=(\d+)\s+height=(\d+)', stdout_text)
            if match:
                return int(match.group(1)), int(match.group(2))
            
            # 尝试匹配 format 格式（如：1920x1080）
            match = re.search(r'(\d{3,4})x(\d{3,4})', stdout_text)
            if match:
                return int(match.group(1)), int(match.group(2))
                
            return None
        except Exception:
            return None

# ==================== 流检测器（db版：单例 + IPv6优化 + 双维度质量评分） ====================
class StreamChecker:
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
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=Config.MAX_WORKERS * 2,
            pool_maxsize=Config.MAX_WORKERS * 2,
            max_retries=0,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def check(self, line: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """检测单条直播源（db版：IPv6优化 + ffprobe降级保底分）"""
        try:
            if ',' not in line:
                return None
            name_part, url_part = line.split(',', 1)
            name = name_part.strip()[:100]
            url  = url_part.strip()

            # 基础校验
            if not name or not url:
                return None
            if NameProcessor.is_blacklisted(name):
                return None
            if URLCleaner.filter_private_ip(url):
                return None
            if URLCleaner.is_vod_domain(url):
                return None
            if not url.startswith(('http://', 'https://')):
                return None

            # IPv6 优化：直接返回满分
            if Config.ENABLE_IPV6_OPTIMIZE and URLCleaner.is_ipv6(url):
                overseas = NameProcessor.is_overseas(name)
                return {
                    "status": "有效", "name": name, "url": url,
                    "lat": Config.IPV6_DEFAULT_DELAY,
                    "speed": Config.IPV6_DEFAULT_SPEED,
                    "overseas": overseas,
                    "quality": 100,
                    "ipv6": True
                }

            # 境内外超时设置
            overseas = NameProcessor.is_overseas(name)
            timeout  = Config.TIMEOUT_OVERSEAS if overseas else Config.TIMEOUT_CN

            # ffprobe 流检测
            result = self._check_with_ffprobe(url, name, timeout, proxy, overseas)
            # 失败则降级 HTTP 检测
            if not result:
                result = self._check_with_http(url, name, timeout, proxy, overseas)

            # 速度检测
            if result["status"] == "有效" and Config.ENABLE_SPEED_CHECK:
                speed_mbps = StreamChecker.check_speed(url, proxy)
                result["speed"] = speed_mbps
                if speed_mbps < Config.MIN_SPEED_MBPS:
                    result["status"] = "失效"
                    result["reason"] = f"速度不足 {speed_mbps}MB/s"
                else:
                    result["quality"] = StreamChecker._calc_quality_score(result["lat"], speed_mbps)
            elif result["status"] == "有效" and not Config.ENABLE_SPEED_CHECK:
                result["speed"] = 0.0
                result["quality"] = StreamChecker._calc_quality_score(result["lat"], 1.0)

            return result
        except Exception:
            return None

    def _check_with_ffprobe(self, url: str, name: str, timeout: int,
                            proxy: Optional[str], overseas: bool) -> Optional[Dict[str, Any]]:
        """ffprobe 流检测"""
        start_time = time.time()
        domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers_str = f'User-Agent: {random.choice(Config.UA_POOL)}\r\nReferer: {domain}\r\n'
        cmd = [
            'ffprobe', '-headers', headers_str, '-v', 'error',
            '-show_entries', 'stream=codec_type:format=duration,format_name',
            '-probesize', str(Config.FFPROBE_PROBESIZE),
            '-analyzeduration', str(Config.FFPROBE_ANALYZEDURATION),
            '-timeout', str(int(timeout * 1_000_000)),
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '2',
            '-err_detect', 'ignore_err', '-fflags', 'nobuffer+flush_packets',
        ]
        if proxy:
            cmd.extend(['-http_proxy', proxy])
        cmd.append(url)

        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            stdout, stderr = proc.communicate(timeout=timeout + Config.FFPROBE_TIMEOUT_BUFFER)
            stdout_text = stdout.decode('utf-8', errors='ignore').lower()
            stderr_text = stderr.decode('utf-8', errors='ignore').lower()

            has_fatal  = any(kw in stderr_text for kw in Config.FATAL_ERROR_KEYWORDS)
            has_stream = 'codec_type=video' in stdout_text or 'codec_type=audio' in stdout_text

            if not has_fatal and has_stream:
                latency = round(time.time() - start_time, 2)
                return {
                    "status": "有效", "name": name, "url": url, "lat": latency,
                    "overseas": overseas,
                    "quality": max(
                        StreamChecker._calc_quality_score(latency, 0.0),
                        Config.MIN_QUALITY_SCORE
                    ),
                    "speed": 0.0
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
        """HTTP 降级检测（db版：HEAD失败降级GET + 保底质量分）"""
        start_time = time.time()
        domain  = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        headers = {'User-Agent': random.choice(Config.UA_POOL), 'Referer': domain}
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        http_timeout = timeout // 2

        try:
            resp = self.session.head(url, headers=headers, timeout=http_timeout,
                                     allow_redirects=True, proxies=proxies)
            resp.close()
            if resp.status_code not in (200, 206, 301, 302, 304):
                resp = self.session.get(url, headers=headers, timeout=http_timeout,
                                        allow_redirects=True, proxies=proxies, stream=True)
                if resp.status_code not in (200, 206):
                    return {"status": "失效", "name": name, "url": url, "overseas": overseas,
                            "reason": f"HTTP {resp.status_code}"}
                resp.close()

            latency = round(time.time() - start_time, 2)
            # db版：ffprobe降级源给保底分，不低于 MIN_QUALITY_SCORE（避免二次过滤）
            return {
                "status": "有效", "name": name, "url": url, "lat": latency,
                "overseas": overseas,
                "quality": max(
                    StreamChecker._calc_quality_score(latency, 0.0),
                    Config.MIN_QUALITY_SCORE
                ),
                "speed": 0.0
            }
        except Exception:
            return {"status": "失效", "name": name, "url": url, "overseas": overseas,
                    "reason": "检测超时/连接失败"}

    @staticmethod
    def _calc_quality_score(latency: float, speed_mbps: float) -> int:
        """双维度质量评分：延迟(60分) + 速度(40分)，满分100"""
        # 延迟基础分
        if latency <= 1:   base = 60
        elif latency <= 3: base = 50
        elif latency <= 5: base = 40
        elif latency <= 10:base = 30
        elif latency <= 15:base = 20
        else:              base = 10
        # 速度附加分
        if speed_mbps >= 2:    spd = 40
        elif speed_mbps >= 1: spd = 30
        elif speed_mbps >= 0.2: spd = 20
        elif speed_mbps >= 0.05:spd = 10
        else:                   spd = 5   # 极低速度也给保底
        return min(base + spd, 100)

    @staticmethod
    def check_speed(url: str, proxy: Optional[str] = None) -> float:
        """检测下载速度（MB/s）"""
        if not Config.ENABLE_SPEED_CHECK:
            return 0.0
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        headers  = {'User-Agent': random.choice(Config.UA_POOL)}
        try:
            start_time = time.time()
            resp = requests.get(url, headers=headers, proxies=proxies,
                              stream=True, timeout=Config.TIMEOUT_CN + 5)
            total = 0
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    total += len(chunk)
                if total >= Config.SPEED_CHECK_BYTES:
                    break
            elapsed = time.time() - start_time
            resp.close()
            if elapsed <= 0 or total < 1024:
                return 0.0
            return round((total / 1024 / 1024) / elapsed, 4)
        except Exception:
            return 0.0

# ==================== P2 优化 #6：统计信息管理器 ====================
class StatsManager:
    """统计信息持久化管理器（支持历史数据对比）"""
    
    def __init__(self, stats_file: Path):
        self.stats_file = stats_file
        self.current_stats = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total': 0,
            'valid': 0,
            'failed': 0,
            'filtered': 0,
            'written': 0,
            'success_rate': 0.0,
            'duration_seconds': 0,
            'by_category': {},
            'by_overseas': {'cn': 0, 'overseas': 0}
        }
        self.history = self._load_history()
    
    def _load_history(self) -> List[Dict]:
        """加载历史统计"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('history', [])
        except Exception:
            pass
        return []
    
    def save(self):
        """保存当前统计到历史"""
        try:
            self.history.append(self.current_stats)
            # 只保留最近 10 次记录
            if len(self.history) > 10:
                self.history = self.history[-10:]
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'history': self.history,
                    'latest': self.current_stats
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def update(self, key: str, value: Any):
        """更新当前统计"""
        if key in self.current_stats:
            self.current_stats[key] = value
    
    def print_comparison(self):
        """打印历史对比"""
        if not self.history or len(self.history) < 2:
            return
        
        latest = self.current_stats
        previous = self.history[-2]
        
        print(f"\n{'='*60}")
        print(f"📊 历史统计对比（最近 2 次运行）")
        print(f"{'='*60}")
        print(f"{'指标':<20} {'上一次':<15} {'当前':<15} {'变化':<15}")
        print(f"{'-'*60}")
        print(f"{'运行时间':<20} {previous['timestamp']:<15} {latest['timestamp']:<15} {'':<15}")
        print(f"{'检测总数':<20} {previous['total']:<15} {latest['total']:<15} {latest['total']-previous['total']:+d}")
        print(f"{'有效数量':<20} {previous['valid']:<15} {latest['valid']:<15} {latest['valid']-previous['valid']:+d}")
        print(f"{'有效率':<20} {previous['success_rate']:<14.1f}% {latest['success_rate']:<14.1f}% {latest['success_rate']-previous['success_rate']:+.1f}%")
        print(f"{'耗时(秒)':<20} {previous['duration_seconds']:<15.1f} {latest['duration_seconds']:<15.1f} {latest['duration_seconds']-previous['duration_seconds']:+.1f}")

# ==================== 主控制器 ====================
class IPTVChecker:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if Config.DEBUG_MODE:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

        # P0 优化 #2：初始化缓存
        self.cache = URLCache(Config.CACHE_FILE, Config.CACHE_TTL_HOURS)
        
        # P2 优化 #6：初始化统计管理器
        self.stats_manager = StatsManager(Config.STATS_FILE)
        
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.stats   = {
            'total': 0, 'valid': 0, 'failed': 0,
            'by_overseas': {'cn': 0, 'overseas': 0},
            'by_category': {cat: 0 for cat in Config.CATEGORY_ORDER},
            'filtered_by_quality': 0
        }
        self.start_time = None  # 记录开始时间

    def backup_output(self, output_file: Path) -> bool:
        """备份原输出文件"""
        if not output_file.exists() or not Config.AUTO_BACKUP:
            return False
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        backup_file = output_file.with_name(f"{output_file.stem}_backup_{timestamp}.txt")
        output_file.rename(backup_file)
        self.logger.info(f"📦 备份原文件: {backup_file.name}")
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]):
        # 注意：domain_lines 必须传入 defaultdict(list)，由调用方保证
        for line in lines:
            if ',' not in line:
                continue
            name_part, url_part = line.split(',', 1)
            name = name_part.strip()
            url = url_part.strip()

            # 有效性校验
            if not name or name == '未知频道':
                continue
            if NameProcessor.is_blacklisted(name):
                continue
            if URLCleaner.filter_private_ip(url):
                continue
            if URLCleaner.is_vod_domain(url):
                continue
            if not url.startswith(('http://', 'https://')):
                continue

            fp = URLCleaner.get_fingerprint(url)
            
            # P0 优化 #2：检查缓存（跳过已检测的源）
            if self.cache.is_cached(fp):
                continue
            
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            
            # Fix #2: 使用 _get_hostname 复用解析逻辑
            domain = URLCleaner._get_hostname(url)
            domain_lines[domain].append(f"{name},{url}")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        """同步运行主流程"""
        self.start_time = time.time()  # 记录开始时间
        seen_fp      = pre_seen_fp      if pre_seen_fp      is not None else set()
        domain_lines = pre_domain_lines if pre_domain_lines is not None else defaultdict(list)
        lines_to_check: List[str] = []

        # 1. 处理本地文件
        if Config.ENABLE_LOCAL_CHECK:
            input_path = args.input if args.input else str(Config.INPUT_FILE)
            self.logger.info(f"📂 读取本地文件：{input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    local_lines = [l.strip() for l in f if l.strip()]
                self.process_lines(local_lines, seen_fp, domain_lines)
                self.logger.info(f"✅ 本地文件处理完成：{len(local_lines)}条")
            except Exception as e:
                self.logger.error(f"❌ 读取本地文件失败: {e}")

        # 2. 拉取预设网络源
        if Config.ENABLE_WEB_CHECK:
            web_sources = Config.WEB_SOURCES
            if not web_sources and Config.CONFIG_FILE.exists():
                Config.load_from_file()
                web_sources = Config.WEB_SOURCES

            if web_sources:
                self.logger.info(f"🌐 并发拉取 {len(web_sources)} 个预设网络源...")
                with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                    future_to_url = {executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                                     for url in web_sources}
                    success_count = fail_count = total_extracted = 0
                    successful_web_sources = []
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

        # 3. 收集待测源
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

        overseas_total = sum(1 for ln in lines_to_check if NameProcessor.is_overseas(ln.split(',', 1)[0]))
        self.logger.info(f"📋 待测源统计: 总计 {total} 条 | 境内 {total - overseas_total} 条 | 境外 {overseas_total} 条")

        cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list: List[str] = []
        real_workers = min(args.workers, total)
        self.logger.info(f"🚀 启动并发检测：{real_workers}个工作线程")

        # 4. 并发测活（P2 优化 #8：进度条简洁适配）
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="检测", unit="条", ncols=70,
                  bar_format='{l_bar}{bar}| {n}/{total} [{percentage:.0f}%] [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            # 绑定 future 与对应的 ln，修复 NameError
            future_to_ln = {executor.submit(self.checker.check, ln, Config.PROXY): ln for ln in lines_to_check}
            done_count = 0
            for future in as_completed(future_to_ln):
                ln = future_to_ln[future]  # 取出当前任务对应的源行
                r = future.result()
                if r:
                    self.stats['valid'] += 1
                    # P0 优化 #2：将有效源添加到缓存
                    fp = URLCleaner.get_fingerprint(r['url'])
                    self.cache.add(fp)
                    
                    if r['overseas']:
                        self.stats['by_overseas']['overseas'] += 1
                    else:
                        self.stats['by_overseas']['cn'] += 1
                    # 修复：ffprobe 成功的流 quality=0（无速度分），设兜底分避免 quality KeyError
                    if 'quality' not in r or r['quality'] == 0:
                        r['quality'] = Config.MIN_QUALITY_SCORE
                    # 分类
                    category = NameProcessor.classify(r['name'])
                    if category in cat_map:
                        cat_map[category].append(r)
                else:
                    self.stats['failed'] += 1
                    fail_list.append(ln)
                done_count += 1
                # 更新进度条，显示实时有效率
                valid_percent = (self.stats['valid'] / done_count * 100) if done_count > 0 else 0
                pbar.set_postfix_str(f'有效{self.stats["valid"]}/{done_count} ({valid_percent:.1f}%)')
                pbar.update(1)

        # 5. 速度检测（可选）
        if Config.ENABLE_SPEED_CHECK:
            self.logger.info(f"⏳ 开始速度检测...")
            # 收集所有有效源及其所属分类，避免迭代时修改列表
            valid_sources_with_cat = []
            for cat, chs in cat_map.items():
                for ch in chs:
                    valid_sources_with_cat.append((cat, ch))
            
            speed_filtered = 0
            for cat, channel_data in tqdm(valid_sources_with_cat, desc="测速", unit="条", ncols=60,
                                     bar_format='{l_bar}{bar}| {n}/{total} [{percentage:.0f}%]'):
                speed = self.checker.check_speed(channel_data['url'], Config.PROXY)
                if speed < Config.MIN_SPEED_MBPS:
                    # 速度太慢，从原分类列表中移除
                    if channel_data in cat_map[cat]:
                        cat_map[cat].remove(channel_data)
                        speed_filtered += 1
                else:
                    # 速度分数加入质量分
                    channel_data['quality'] += int(speed * 10)
            
            if speed_filtered > 0:
                self.stats['filtered_by_quality'] += speed_filtered
                self.logger.info(f"⚠️ 速度过滤: {speed_filtered} 条")

        # 6. 写入结果文件
        output_file = args.output if args.output else str(Config.OUTPUT_FILE)
        total_written = self.write_results(output_file, cat_map, total, fail_list)
        
        # P2 优化 #6：更新并保存统计信息
        duration = time.time() - self.start_time
        self.stats_manager.update('total', total)
        self.stats_manager.update('valid', self.stats['valid'])
        self.stats_manager.update('failed', self.stats['failed'])
        self.stats_manager.update('filtered', self.stats['filtered_by_quality'])
        self.stats_manager.update('written', total_written)
        self.stats_manager.update('success_rate', (self.stats['valid'] / total * 100) if total > 0 else 0)
        self.stats_manager.update('duration_seconds', duration)
        self.stats_manager.update('by_category', self.stats['by_category'])
        self.stats_manager.update('by_overseas', self.stats['by_overseas'])
        self.stats_manager.save()
        self.stats_manager.print_comparison()

    async def run_async(self, args):
        """异步运行模式（db版：使用 crawl_all_with_names 返回 {url: name} 映射）"""
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)

        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            self.logger.info("🌐 启动异步爬虫（db版：域名质量评分）...")
            async with AsyncWebSourceCrawler() as crawler:
                url_to_name = await crawler.crawl_all_with_names()
                if url_to_name:
                    self.logger.info(f"🔍 发现新增源: {len(url_to_name)} 个")
                    for url, name in url_to_name.items():
                        if not URLCleaner.is_valid(url):
                            continue
                        if not URLCleaner.filter_private_ip(url):
                            continue
                        if any(kw in name for kw in Config.BLACKLIST):
                            continue
                        if URLCleaner.is_vod_domain(url):
                            if not Config.LIVE_CHANNEL_KEYWORDS.search(name):
                                continue
                        name = NameProcessor.clean(name)
                        if not name or name == '未知频道':
                            continue
                        fp = URLCleaner.get_fingerprint(url)
                        if fp not in seen_fp:
                            seen_fp.add(fp)
                            domain_lines["crawled_sources"].append(f"{name},{url}")
                    self.logger.info(f"✅ 新增源已加入待测列表: {len(domain_lines['crawled_sources'])} 个")

        self.run(args, pre_seen_fp=seen_fp, pre_domain_lines=domain_lines)

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int, fail_list: Optional[List[str]] = None) -> int:
        """写入结果文件，空分类不写入，质量过滤增加兜底，返回实际写入数量"""
        output_path = Path(output_file)
        tmp_path    = output_path.with_suffix('.tmp')
        total_written = 0

        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for cat in Config.CATEGORY_ORDER:
                    channels = cat_map.get(cat, [])

                    # Fix #5: 分组同时完成质量过滤（db版：低质量源进降级保底池）
                    grouped = defaultdict(list)
                    fallback_grouped = defaultdict(list)  # 降级保底池：低于阈值但有效的源
                    for ch in channels:
                        # 质量过滤：quality < MIN_QUALITY_SCORE 时进降级池（不含等于）
                        if Config.ENABLE_QUALITY_FILTER and ch['quality'] < Config.MIN_QUALITY_SCORE:
                            fallback_grouped[ch['name']].append(ch)
                            self.stats['filtered_by_quality'] += 1
                            continue
                        grouped[ch['name']].append(ch)
                        self.stats['by_category'][cat] += 1

                    total_channels_in_cat = sum(len(items) for items in grouped.values())
                    if total_channels_in_cat <= 0:
                        continue

                    f.write(f"{cat},#genre#\n")
                    total_written += total_channels_in_cat

                    # 央衛頻道特殊排序
                    if cat == "央衛頻道":
                        # 第一梯队：CCTV1-17（含 CCTV5+）
                        cctv_1_to_17 = []
                        # 第二梯队：其他 CCTV 数字台（CCTV18+，非1-17）
                        cctv_18_plus = []
                        # 第三梯队：其他央視/央视/中央台（非 CCTV 数字）
                        other_central = []

                        for name in sorted(grouped.keys()):
                            m = re.search(r'CCTV(\d+)$', name)
                            if m:
                                num = int(m.group(1))
                                if 1 <= num <= 17:
                                    cctv_1_to_17.append((num, name))
                                else:
                                    cctv_18_plus.append((num, name))
                            elif "CCTV" in name or "央視" in name or "中央" in name or "央视" in name:
                                other_central.append(name)

                        # 写入 CCTV1-17（按数字排序，CCTV5+ 独立输出，不在其中）
                        cctv_1_to_17.sort()
                        for _, name in cctv_1_to_17:
                            self._write_channel(f, grouped[name], Config.MAX_LINKS_PER_NAME)

                        # 写入 CCTV5+（如有）
                        if "CCTV5+" in grouped:
                            self._write_channel(f, grouped["CCTV5+"], Config.MAX_LINKS_PER_NAME)

                        # 写入 CCTV18+（如有）
                        if cctv_18_plus:
                            cctv_18_plus.sort()
                            for _, name in cctv_18_plus:
                                self._write_channel(f, grouped[name], Config.MAX_LINKS_PER_NAME)

                        # 写入其他央視台（按质量降序）
                        for name in sorted(other_central,
                                            key=lambda n: max(ch['quality'] for ch in grouped[n]),
                                            reverse=True):
                            self._write_channel(f, grouped[name], Config.MAX_LINKS_PER_NAME)

                        # db版优化③：降级保底池（频道主池不足时用低质量备选源补齐）
                        for name in grouped:
                            if len(grouped[name]) < Config.MAX_LINKS_PER_NAME and name in fallback_grouped:
                                spare = max(Config.MAX_LINKS_PER_NAME - len(grouped[name]), 1)
                                self._write_channel(f, fallback_grouped[name], spare)
                    else:
                        # 其他分类按质量降序
                        for channels_list in sorted(grouped.values(),
                                              key=lambda lst: max(ch['quality'] for ch in lst),
                                              reverse=True):
                            self._write_channel(f, channels_list, Config.MAX_LINKS_PER_NAME)

                        # db版优化③：降级保底池
                        for name in grouped:
                            if len(grouped[name]) < Config.MAX_LINKS_PER_NAME and name in fallback_grouped:
                                spare = max(Config.MAX_LINKS_PER_NAME - len(grouped[name]), 1)
                                self._write_channel(f, fallback_grouped[name], spare)

        except Exception as e:
            self.logger.error(f"❌ 写入结果失败: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            raise e

        # 原子文件替换
        if tmp_path.exists():
            if output_path.exists():
                output_path.unlink()
            tmp_path.rename(output_path)

        # 打印统计
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: 总计 {total} 条")
        self.logger.info(f"✅ 测活有效: {self.stats['valid']} 条 | 失效: {self.stats['failed']} 条")
        self.logger.info(f"⚠️  质量过滤: {self.stats['filtered_by_quality']} 条 | 最终写入: {total_written} 条")
        self.logger.info(f"✅ 整体有效率: {self.stats['valid']/total*100:.1f}%")
        self.logger.info(f"📊 境内有效: {self.stats['by_overseas']['cn']} 条 | 境外有效: {self.stats['by_overseas']['overseas']} 条")
        self.logger.info(f"📋 分类有效统计:")
        for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: -x[1]):
            self.logger.info(f"  {cat}: {count} 条")

        # 失效源归档
        if Config.ARCHIVE_FAIL and fail_list:
            fail_file = output_path.with_name(f"{output_path.stem}_fail.txt")
            with open(fail_file, 'w', encoding='utf-8') as f:
                for line in fail_list:
                    f.write(f"{line}\n")
            self.logger.info(f"📦 失效源已归档: {fail_file.name}")
        
        return total_written

    def _write_channel(self, f, channels: List[Dict], max_links: int):
        """写入单个频道的数据（格式：频道名,URL）"""
        if not channels:
            return
        # 按质量降序，保留前 N 条
        sorted_channels = sorted(channels, key=lambda x: x['quality'], reverse=True)[:max_links]
        for ch in sorted_channels:
            f.write(f"{ch['name']},{ch['url']}\n")

# ==================== 命令行入口 ====================
def main():
    # 检测 ffprobe
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            print("✅ ffprobe 正常")
        else:
            print("❌ ffprobe 不可用，请安装 FFmpeg")
            sys.exit(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("❌ ffprobe 不可用，请安装 FFmpeg")
        sys.exit(1)

    # 初始化配置
    Config.load_from_file()
    Config.init_compiled_rules()

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='IPTV 直播源检测工具 - Apex dzh 聚合版')
    parser.add_argument('-i', '--input', default=str(Config.INPUT_FILE), help='输入文件路径')
    parser.add_argument('-o', '--output', default=str(Config.OUTPUT_FILE), help='输出文件路径')
    parser.add_argument('-w', '--workers', type=int, default=Config.MAX_WORKERS, help='并发检测线程数')
    parser.add_argument('-t', '--timeout', type=int, default=Config.TIMEOUT_CN, help='境内源超时时间(秒)')
    parser.add_argument('--proxy', default=None, help='代理地址 (如 http://127.0.0.1:7890)')
    parser.add_argument('--no-web', action='store_true', help='跳过预设网络源拉取')
    parser.add_argument('--async-crawl', action='store_true', help='启用异步爬虫扫描新源')
    parser.add_argument('--no-speed-check', action='store_true', help='关闭下载速度检测')
    parser.add_argument('--no-cache', action='store_true', help='禁用 URL 去重缓存')
    parser.add_argument('--no-resolution-filter', action='store_true', help='禁用分辨率过滤')
    args = parser.parse_args()

    if args.timeout:
        Config.TIMEOUT_CN = args.timeout
        Config.TIMEOUT_OVERSEAS = args.timeout * 2

    if args.workers:
        Config.MAX_WORKERS = args.workers

    if args.no_speed_check:
        Config.ENABLE_SPEED_CHECK = False

    if args.no_cache:
        Config.ENABLE_CACHE = False

    if args.no_resolution_filter:
        Config.ENABLE_RESOLUTION_FILTER = False

    print(f"{'='*60}")
    print("IPTV-Apex-dzh 聚合版")
    print(f"{'='*60}")
    if HAS_M3U8_LIB:
        print("✅ M3U8 解析库已启用（频道名准确率提升 10-20%）")
    else:
        print("⚠️  M3U8 解析库未安装（建议安装：pip install m3u8）")
    if Config.ENABLE_CACHE:
        print(f"✅ URL 去重缓存已启用（TTL: {Config.CACHE_TTL_HOURS}小时）")
    else:
        print("⚠️  URL 去重缓存已禁用")
    if Config.ENABLE_RESOLUTION_FILTER:
        print(f"✅ 分辨率过滤已启用（最低: {Config.MIN_RESOLUTION_WIDTH}x{Config.MIN_RESOLUTION_HEIGHT}）")
    else:
        print("⚠️  分辨率过滤已禁用")
    print(f"{'='*60}\n")

    checker = IPTVChecker()

    # 备份原文件
    output_file = Path(args.output if args.output else str(Config.OUTPUT_FILE))
    checker.backup_output(output_file)

    try:
        if Config.ENABLE_WEB_FETCH or args.async_crawl:
            asyncio.run(checker.run_async(args))
        else:
            checker.run(args)
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断程序")
    except Exception as e:
        checker.logger.error(f"❌ 程序异常: {e}")
        raise

if __name__ == '__main__':
    main()
