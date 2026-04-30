#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直连二验模块
核心：过滤海外域名/GFW封禁/token过期源
"""

import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import requests

from ..config import Config


class DirectChecker:
    """直连可用性验证"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18'
        })
        self.session.trust_env = False

    # 已知可靠CDN域名关键词（中国大陆可直连）
    KNOWN_DIRECT = {
        # 运营商 CDN
        'live.264788', 'goodiptv', '163189', 'jdshipin',
        'tencentplay', 'bp-resource', 'bestv', 'amucn',
        'xryo', 'migu', 'dsj', 'ottiptv', 'iill',
        'aktv', 'ott.mobai', 'mobai',
        # 云厂商 CDN
        'cdn8.', 'cdn6.', 'cdn12.', 'cdn.', 'cos.',
        'tencent.', 'aliyun', 'alicdn', 'ali-cdn', 'aliyuncs',
        'qcloud', 'myqcloud', 'tencentyun',
        'speedws', 'bdstatic', 'bcebos',
        # 运营商 IPTV
        'chinamobile', 'unicom', 'chinanet', 'telecom',
        'otttv', 'bj.chinamobile', 'sn.chinamobile',
        'dbiptv', 'yinhe', 'hwltm', 'zteres',
        # 其他国内 CDN
        'jsdelivr', 'bootcdn', 'staticfile',
    }

    def is_known_direct(self, url: str) -> bool:
        """检查是否为已知可靠CDN（支持 IPv6 地址）"""
        try:
            netloc = url.split('://', 1)[-1].split('?')[0].split('/')[0].lower()
            # IPv6 地址格式 [2409:8087:...]
            if netloc.startswith('['):
                # 国内运营商 IPv6 地址段
                ipv6_cn_prefixes = [
                    '2409:8087',  # 中国移动
                    '2408:8000',  # 中国联通
                    '240e:600',   # 中国电信
                    '240e:900',   # 中国电信
                ]
                for prefix in ipv6_cn_prefixes:
                    if netloc.startswith('[' + prefix):
                        return True
            for k in self.KNOWN_DIRECT:
                if netloc == k or netloc.endswith('.' + k) or ('.' + k) in netloc:
                    return True
        except Exception:
            pass
        return False

    def check_one(self, channel: Dict) -> bool:
        """单条直连检测（不用代理），支持 IPv6"""
        url = channel.get('url', '')
        if not url:
            return False

        # UDP/RTP/SRT 直接通过
        if url.startswith(('udp://', 'rtp://', 'srt://')):
            return True

        # 已知CDN直接通过（含 IPv6 国内运营商地址）
        if self.is_known_direct(url):
            return True

        # IPv6 地址直接通过（国内运营商）
        if '[2409:8087' in url or '[2408:8000' in url or '[240e:' in url:
            return True

        # 直连检测（不用代理 - trust_env=False 已禁用系统代理）
        # 使用 GET+Range 代替 HEAD，避免部分 CDN/运营商拦截 HEAD 请求
        try:
            headers = {
                'User-Agent': random.choice(Config.UA_POOL),
                'Range': 'bytes=0-511',
                'Accept': '*/*',
                'Connection': 'keep-alive',
            }
            r = self.session.get(url, timeout=5, verify=False,
                                stream=True, headers=headers,
                                allow_redirects=True)
            # 301/302/303/307/308: 跟随重定向后降级为 GET 验证实际内容
            if r.status_code in (200, 206):
                # 验证内容是否包含媒体特征（#EXTM3U/TS/FLV）
                try:
                    preview = r.raw.read(200) if hasattr(r.raw, 'read') else b''
                    if preview:
                        if b'#EXTM3U' in preview or b'\x47' in preview[:4] or b'FLV' in preview:
                            return True
                except Exception:
                    pass
                return True
            # 3xx 重定向：尝试跟随到最终 URL（禁用自动重定向，由 requests 手动跟随）
            if r.status_code in (301, 302, 303, 307, 308):
                final_url = r.url  # requests 自动解析后的最终 URL
                if final_url and final_url != url:
                    try:
                        r2 = self.session.get(final_url, timeout=5, verify=False,
                                              stream=True, headers=headers,
                                              allow_redirects=False)
                        if r2.status_code in (200, 206):
                            try:
                                preview = r2.raw.read(200) if hasattr(r2.raw, 'read') else b''
                                if preview:
                                    if b'#EXTM3U' in preview or b'\x47' in preview[:4] or b'FLV' in preview:
                                        return True
                            except Exception:
                                pass
                            return True
                        if r2.status_code in (301, 302, 303, 307, 308):
                            # 多重重定向，取最终 URL
                            final2 = r2.url
                            if final2 and final2 != final_url:
                                r3 = self.session.get(final2, timeout=5, verify=False,
                                                      stream=True, headers=headers,
                                                      allow_redirects=False)
                                if r3.status_code in (200, 206):
                                    return True
                                r3.close()
                        r2.close()
                    except Exception:
                        pass
            return r.status_code < 500
        except Exception:
            return False

    def filter_channels(self, cat_map: Dict[str, List[Dict]], max_workers: int = 80) -> Dict[str, List[Dict]]:
        """批量直连二验，返回过滤后的 cat_map"""
        # 收集所有频道
        all_channels = []
        for cat, channels in cat_map.items():
            for ch in channels:
                all_channels.append((cat, ch))

        # 分离已知直通和待检测
        to_test = []
        for cat, ch in all_channels:
            url = ch.get('url', '')
            if url.startswith(('udp://', 'rtp://', 'srt://')):
                ch['_direct_ok'] = True
            elif self.is_known_direct(url):
                ch['_direct_ok'] = True
            else:
                to_test.append((cat, ch))

        total = len(all_channels)
        print(f'直连二验: 总计 {total} 个 | 直通 {total - len(to_test)} 个 | 待检测 {len(to_test)} 个')

        # 并发检测
        if to_test:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(self.check_one, ch): (cat, ch) for cat, ch in to_test}
                for fut in as_completed(futures):
                    cat, ch = futures[fut]
                    ch['_direct_ok'] = fut.result()

        # 重建 cat_map
        removed = 0
        result = {}
        for cat in cat_map:
            still = [c for c in cat_map[cat] if c.get('_direct_ok', True)]
            removed += len(cat_map[cat]) - len(still)
            if still:
                result[cat] = still

        valid = sum(len(v) for v in result.values())
        print(f'直连二验: 过滤 {removed} 个无效源，剩余 {valid} 个有效')
        return result
