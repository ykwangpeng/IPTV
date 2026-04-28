#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分辨率检测辅助
"""

import re
import subprocess
from typing import Optional, Tuple

from ..config import Config


class ResolutionDetector:
    """基于 ffprobe 的分辨率检测"""

    @staticmethod
    def parse_resolution(stdout_text: str) -> Optional[Tuple[int, int]]:
        """从 ffprobe 输出解析分辨率"""
        try:
            width_match = re.search(r'width=(\d+)', stdout_text)
            height_match = re.search(r'height=(\d+)', stdout_text)
            if width_match and height_match:
                return int(width_match.group(1)), int(height_match.group(1))
        except Exception:
            pass
        return None

    @staticmethod
    def detect(url: str, timeout: int = 10) -> Optional[Tuple[int, int]]:
        """使用 ffprobe 检测分辨率"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=s=x:p=0',
                '-probesize', str(Config.FFPROBE_PROBESIZE),
                '-analyzeduration', str(Config.FFPROBE_ANALYZEDURATION),
                '-timeout', str(timeout * 1000000),
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0 and 'x' in result.stdout:
                w, h = result.stdout.strip().split('x')
                return int(w), int(h)
        except Exception:
            pass
        return None
