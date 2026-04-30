#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频道名称处理工具
优化：
  1. 繁体统一转简体
  2. 英文字母统一转大写
  3. 加强噪音清洗
  4. 规范化名称用于去重
"""

import re
import zhconv
from typing import Dict, Optional

from ..config import Config


class NameProcessor:
    """频道名称处理"""

    _simplify_cache: Dict[str, str] = {}
    _normalize_cache: Dict[str, str] = {}

    # 噪音模式（括号、特殊符号、分辨率标识等）
    NOISE_PATTERNS = [
        # 各类括号及其内容
        r'[\(\[\{【＜『「『（][^\)\]\}】＞』」』）]*[\)\]\}】＞』」』）]?',
        # 分辨率/画质标识
        r'\b(1080[PI]?|720[PI]?|480[PI]?|360[PI]?|4K|8K|UHD|HDR|SD|HD|FHD)\b',
        # 码率/帧率
        r'\d{3,5}[Kk][Bb]?[Pp]?[Ss]?',
        # 源标识
        r'(源|线路|节点|备|主|副|HD|SD|高清|标清|超清|蓝光|原画|流畅)[123]?',
        # 状态标识
        r'(在线|离线|测试|正式|备用|主用)',
        # 时间标识
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
        r'\d{1,2}:\d{2}',
        # 特殊字符
        r'[★☆●○◆◇■□▲△▶▼◀♢♤♧♡♢♠♣♥♦]',
    ]

    # 频道名规范化映射（常见别名统一）
    # 注意：键名全部大写，因为 normalize 方法会先转大写
    NAME_ALIASES = {
        # CCTV 系列（统一为 CCTV-N 格式）
        'CCTV1': 'CCTV-1', 'CCTV2': 'CCTV-2', 'CCTV3': 'CCTV-3',
        'CCTV4': 'CCTV-4', 'CCTV5': 'CCTV-5', 'CCTV6': 'CCTV-6',
        'CCTV7': 'CCTV-7', 'CCTV8': 'CCTV-8', 'CCTV9': 'CCTV-9',
        'CCTV10': 'CCTV-10', 'CCTV11': 'CCTV-11', 'CCTV12': 'CCTV-12',
        'CCTV13': 'CCTV-13', 'CCTV14': 'CCTV-14', 'CCTV15': 'CCTV-15',
        'CCTV16': 'CCTV-16', 'CCTV17': 'CCTV-17',
        'CCTV5PLUS': 'CCTV-5+', 'CCTV5+': 'CCTV-5+',
        '中央一台': 'CCTV-1', '中央二台': 'CCTV-2', '中央三台': 'CCTV-3',
        '中央四台': 'CCTV-4', '中央五台': 'CCTV-5', '中央六台': 'CCTV-6',
        '中央七台': 'CCTV-7', '中央八台': 'CCTV-8',
        '中央1台': 'CCTV-1', '中央2台': 'CCTV-2', '中央3台': 'CCTV-3',
        '中央4台': 'CCTV-4', '中央5台': 'CCTV-5', '中央6台': 'CCTV-6',
        '中央7台': 'CCTV-7', '中央8台': 'CCTV-8',
        '央视一套': 'CCTV-1', '央视二套': 'CCTV-2', '央视三套': 'CCTV-3',
        '央视四套': 'CCTV-4', '央视五套': 'CCTV-5', '央视六套': 'CCTV-6',
        '央视七套': 'CCTV-7', '央视八套': 'CCTV-8',
        '央视1套': 'CCTV-1', '央视2套': 'CCTV-2', '央视3套': 'CCTV-3',
        '央视4套': 'CCTV-4', '央视5套': 'CCTV-5', '央视6套': 'CCTV-6',
        '央视7套': 'CCTV-7', '央视8套': 'CCTV-8',
        '综合频道': 'CCTV-1', '经济频道': 'CCTV-2', '综艺频道': 'CCTV-3',
        '中文国际': 'CCTV-4', '体育频道': 'CCTV-5', '电影频道': 'CCTV-6',
        '国防军事': 'CCTV-7', '电视剧频道': 'CCTV-8', '纪录频道': 'CCTV-9',
        '科教频道': 'CCTV-10', '戏曲频道': 'CCTV-11', '社会与法': 'CCTV-12',
        '新闻频道': 'CCTV-13', '少儿频道': 'CCTV-14', '音乐频道': 'CCTV-15',
        '奥林匹克': 'CCTV-16', '农业农村': 'CCTV-17',
        '中央九台': 'CCTV-9', '中央十台': 'CCTV-10', '中央十一台': 'CCTV-11',
        '中央十二台': 'CCTV-12', '中央十三台': 'CCTV-13', '中央十四台': 'CCTV-14',
        '中央十五台': 'CCTV-15', '中央十六台': 'CCTV-16', '中央十七台': 'CCTV-17',
        '中央9台': 'CCTV-9', '中央10台': 'CCTV-10', '中央11台': 'CCTV-11',
        '中央12台': 'CCTV-12', '中央13台': 'CCTV-13', '中央14台': 'CCTV-14',
        '中央15台': 'CCTV-15', '中央16台': 'CCTV-16', '中央17台': 'CCTV-17',
        # 卫视常见别名（注意：不要把已有卫视后缀的再替换）
        '湖南电视台': '湖南卫视', '浙江电视台': '浙江卫视', '江苏电视台': '江苏卫视',
        '东方电视台': '东方卫视', '北京电视台': '北京卫视', '广东电视台': '广东卫视',
        '山东电视台': '山东卫视', '四川电视台': '四川卫视', '安徽电视台': '安徽卫视',
        '天津电视台': '天津卫视', '河北电视台': '河北卫视', '河南电视台': '河南卫视',
        '湖北电视台': '湖北卫视', '江西电视台': '江西卫视', '重庆电视台': '重庆卫视',
        '福建电视台': '福建卫视', '辽宁电视台': '辽宁卫视', '深圳电视台': '深圳卫视',
        '广西电视台': '广西卫视', '黑龙江电视台': '黑龙江卫视', '云南电视台': '云南卫视',
        '陕西电视台': '陕西卫视', '甘肃电视台': '甘肃卫视', '贵州电视台': '贵州卫视',
        '山西电视台': '山西卫视', '吉林电视台': '吉林卫视', '内蒙古电视台': '内蒙古卫视',
        '宁夏电视台': '宁夏卫视', '新疆电视台': '新疆卫视', '海南电视台': '海南卫视',
        '青海电视台': '青海卫视', '西藏电视台': '西藏卫视',
        '上海卫视': '东方卫视',
        # 港澳台频道别名
        '翡翠台': '翡翠', '明珠台': '明珠', 'TVB翡翠': '翡翠',
        '凤凰卫视中文': '凤凰中文', '凤凰卫视资讯': '凤凰资讯',
        '凤凰卫视': '凤凰', '凤凰': '凤凰',
        'TVBS': 'TVBS新闻', '东森新闻': '东森新闻',
    }

    @classmethod
    def simplify(cls, name: str) -> str:
        """繁简转换（缓存）"""
        if not name:
            return ''
        if name in cls._simplify_cache:
            return cls._simplify_cache[name]
        simplified = zhconv.convert(name, 'zh-cn')
        cls._simplify_cache[name] = simplified
        return simplified

    @classmethod
    def normalize(cls, name: str) -> str:
        """
        频道名规范化（用于去重）：
        1. 繁体转简体
        2. 英文转大写
        3. 去除噪音
        4. 统一别名
        5. 移除 CCTV 频道类型后缀
        """
        if not name:
            return ''
        if name in cls._normalize_cache:
            return cls._normalize_cache[name]

        # 1. 繁体转简体
        normalized = cls.simplify(name)

        # 2. 英文转大写
        normalized = normalized.upper()

        # 3. 去除噪音
        normalized = cls.clean_name(normalized)

        # 4. 统一别名
        # 尝试完全匹配
        if normalized in cls.NAME_ALIASES:
            normalized = cls.NAME_ALIASES[normalized]
        else:
            # 尝试部分匹配
            for alias, standard in cls.NAME_ALIASES.items():
                if alias in normalized:
                    normalized = normalized.replace(alias, standard)
                    break

        # 5. 移除 CCTV 频道类型后缀（如 CCTV-1综合 → CCTV-1）
        # 这些后缀只是频道类型描述，不是频道标识
        cctv_match = re.match(r'(CCTV-?\d+\+?)(综合|财经|综艺|中文国际|体育|电影|国防军事|电视剧|纪录|科教|戏曲|社会与法|新闻|少儿|音乐|奥林匹克|农业农村|体育赛事)?$', normalized)
        if cctv_match:
            normalized = cctv_match.group(1)
            # 统一格式：CCTV-1
            if not normalized.startswith('CCTV-'):
                normalized = normalized.replace('CCTV', 'CCTV-')

        # 6. 移除卫视频道画质后缀（如 湖南卫视高清 → 湖南卫视）
        # 常见画质标识：高清、超清、蓝光、4K、8K、HD、FHD、UHD
        normalized = re.sub(r'(卫视|电视)(高清|超清|蓝光|4K|8K|HD|FHD|UHD|标清)?$', r'\1', normalized)

        # 7. 清理多余空格
        normalized = re.sub(r'\s+', '', normalized)

        cls._normalize_cache[name] = normalized
        return normalized

    @staticmethod
    def is_blacklisted(name: str) -> bool:
        """检查是否在黑名单"""
        name_upper = name.upper()
        return any(kw.upper() in name_upper for kw in Config.BLACKLIST)

    @staticmethod
    def is_overseas(name: str) -> bool:
        """检查是否为境外频道"""
        name_upper = name.upper()
        return any(kw.upper() in name_upper for kw in Config.OVERSEAS_KEYWORDS)

    @classmethod
    def classify(cls, name: str) -> str:
        """频道分类（优先级匹配）"""
        if not name:
            return "其他频道"

        # 规范化后再分类
        simplified = cls.simplify(name)
        upper_name = simplified.upper()

        # 特殊处理：CCTV 系列优先（必须明确包含 CCTV+数字）
        if re.search(r'CCTV[-]?\d', upper_name):
            return "央视频道"

        # 特殊处理：卫视系列（必须包含"卫视"二字）
        if '卫视' in simplified:
            return "卫视频道"

        # 按配置规则匹配
        for cat in Config.CATEGORY_ORDER:
            if cat in ("其他频道", "其他頻道"):
                continue
            compiled = Config.CATEGORY_RULES_COMPILED.get(cat)
            if compiled and compiled.search(simplified):
                return cat

        # 最后检查是否包含"中央""央视"关键词
        if '中央' in simplified or '央视' in simplified:
            return "央视频道"

        return "其他频道"

    @classmethod
    def clean_name(cls, name: str) -> str:
        """清理频道名中的噪音"""
        if not name:
            return ''

        cleaned = name

        # 应用噪音模式
        for pattern in cls.NOISE_PATTERNS:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # 清理连续空格和特殊字符（但保留连字符 - 用于 CCTV-1 等）
        cleaned = re.sub(r'[\s_·•]+', '', cleaned)
        cleaned = re.sub(r'^[\s_·•\-]+|[\s_·•\-]+$', '', cleaned)

        return cleaned.strip()

    @classmethod
    def get_display_name(cls, raw_name: str) -> str:
        """
        获取用于显示的频道名：
        1. 清理噪音
        2. 统一格式
        """
        if not raw_name:
            return ''

        # 繁简转换
        name = cls.simplify(raw_name)

        # 清理噪音
        name = cls.clean_name(name)

        # 格式化 CCTV 名称
        m = re.match(r'CCTV[-\s]*(\d+)(\+)?', name, re.IGNORECASE)
        if m:
            num = m.group(1)
            plus = '+' if m.group(2) else ''
            name = f'CCTV-{num}{plus}'
            # 补充后缀
            if '综合' in raw_name or num == '1':
                name = 'CCTV-1综合'
            elif '财经' in raw_name or num == '2':
                name = 'CCTV-2财经'
            elif '综艺' in raw_name or num == '3':
                name = 'CCTV-3综艺'
            elif '中文国际' in raw_name or num == '4':
                name = 'CCTV-4中文国际'
            elif '体育' in raw_name or num == '5':
                name = 'CCTV-5体育'
            elif '电影' in raw_name or num == '6':
                name = 'CCTV-6电影'
            elif '国防军事' in raw_name or num == '7':
                name = 'CCTV-7国防军事'
            elif '电视剧' in raw_name or num == '8':
                name = 'CCTV-8电视剧'
            elif '纪录' in raw_name or num == '9':
                name = 'CCTV-9纪录'
            elif '科教' in raw_name or num == '10':
                name = 'CCTV-10科教'
            elif '戏曲' in raw_name or num == '11':
                name = 'CCTV-11戏曲'
            elif '社会与法' in raw_name or num == '12':
                name = 'CCTV-12社会与法'
            elif '新闻' in raw_name or num == '13':
                name = 'CCTV-13新闻'
            elif '少儿' in raw_name or num == '14':
                name = 'CCTV-14少儿'
            elif '音乐' in raw_name or num == '15':
                name = 'CCTV-15音乐'
            elif '奥运' in raw_name or num == '16':
                name = 'CCTV-16奥林匹克'
            elif '农业' in raw_name or num == '17':
                name = 'CCTV-17农业农村'

        return name
