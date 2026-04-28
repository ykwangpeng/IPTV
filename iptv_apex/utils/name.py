#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频道名称处理工具
"""

import zhconv

from ..config import Config


class NameProcessor:
    """频道名称处理"""

    _simplify_cache = {}

    @classmethod
    def simplify(cls, name: str) -> str:
        """繁简转换 + 清理"""
        if not name:
            return ''
        if name in cls._simplify_cache:
            return cls._simplify_cache[name]
        simplified = zhconv.convert(name, 'zh-cn')
        cls._simplify_cache[name] = simplified
        return simplified

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
        """频道分类"""
        if not name:
            return "其他頻道"
        simplified = cls.simplify(name)
        for cat in Config.CATEGORY_ORDER:
            if cat == "其他頻道":
                continue
            compiled = Config.CATEGORY_RULES_COMPILED.get(cat)
            if compiled and compiled.search(simplified):
                return cat
        return "其他頻道"

    @staticmethod
    def clean_name(name: str) -> str:
        """清理频道名中的噪音"""
        if not hasattr(Config, '_compiled'):
            Config.init_compiled_rules()
        noise_pattern = Config._compiled.get('noise')
        if noise_pattern:
            name = noise_pattern.sub('', name)
        return name.strip()
