#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计信息管理
"""

import json
import traceback
from pathlib import Path
from typing import Any, Dict


class StatsManager:
    """统计信息持久化"""

    def __init__(self, stats_file: Path):
        self.stats_file = stats_file
        self.data: Dict[str, Any] = {}
        self._load_history()

    def _load_history(self):
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
        except Exception:
            traceback.print_exc()
            self.data = {}

    def update(self, key: str, value: Any):
        self.data[key] = value

    def save(self):
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            traceback.print_exc()

    def print_comparison(self):
        """打印与上次运行的对比"""
        if not self.data:
            return
        print(f"\n{'='*60}")
        print("📊 统计对比")
        for key, value in self.data.items():
            print(f"  {key}: {value}")
