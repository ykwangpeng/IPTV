#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV 检测主流程
"""

import io
import logging
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional, Set

from tqdm import tqdm

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from ..config import Config
from ..utils.url import URLCache, URLCleaner
from ..utils.name import NameProcessor
from ..utils.stats import StatsManager
from ..crawler.sync_fetcher import WebSourceFetcher
from ..crawler.async_crawler import AsyncWebSourceCrawler
from ..checker.stream import StreamChecker
from ..checker.direct import DirectChecker


class IPTVChecker:
    """IPTV 检测主控"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if Config.DEBUG_MODE:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

        self.cache = URLCache(Config.CACHE_FILE, Config.CACHE_TTL_HOURS)
        self.stats_manager = StatsManager(Config.STATS_FILE)
        self.fetcher = WebSourceFetcher()
        self.checker = StreamChecker()
        self.direct_checker = DirectChecker()
        self.stats = {
            'total': 0, 'valid': 0, 'failed': 0,
            'by_overseas': {'cn': 0, 'overseas': 0},
            'by_category': {cat: 0 for cat in Config.CATEGORY_ORDER},
            'filtered_by_quality': 0
        }
        self.start_time = None

    def backup_output(self, output_file: Path) -> bool:
        if not output_file.exists() or not Config.AUTO_BACKUP:
            return False
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        backup_file = output_file.with_name(f"{output_file.stem}_backup_{timestamp}.txt")
        shutil.copy2(output_file, backup_file)
        self.logger.info(f"📦 备份: {backup_file.name}")
        return True

    def process_lines(self, lines: List[str], seen_fp: Set[str], domain_lines: Dict[str, List[str]]):
        stats = {'total': 0, 'no_comma': 0, 'empty_name': 0, 'blacklisted': 0,
                 'private_ip': 0, 'vod_domain': 0, 'bad_url': 0, 'cached': 0,
                 'dup_fp': 0, 'accepted': 0}
        for line in lines:
            stats['total'] += 1
            if ',' not in line:
                stats['no_comma'] += 1
                continue
            name_part, url_part = line.split(',', 1)
            name = name_part.strip()
            url = url_part.strip()

            if not name or name == '未知频道':
                stats['empty_name'] += 1
                continue
            if NameProcessor.is_blacklisted(name):
                stats['blacklisted'] += 1
                continue
            if URLCleaner.filter_private_ip(url):
                stats['private_ip'] += 1
                continue
            if URLCleaner.is_vod_domain(url):
                stats['vod_domain'] += 1
                continue
            if not url.startswith(('http://', 'https://')):
                stats['bad_url'] += 1
                continue

            fp = URLCleaner.get_fingerprint(url)
            if self.cache.is_cached(fp):
                stats['cached'] += 1
                continue
            if fp in seen_fp:
                stats['dup_fp'] += 1
                continue
            seen_fp.add(fp)
            stats['accepted'] += 1

            domain = URLCleaner._get_hostname(url)
            domain_lines[domain].append(f"{name},{url}")

        self.logger.info(f"📊 process_lines: 输入={stats['total']}, 接受={stats['accepted']}")

    def run(self, args, pre_seen_fp: Set[str] = None, pre_domain_lines: Dict = None):
        """同步运行主流程"""
        self.start_time = time.time()
        crawl_domain_lines = pre_domain_lines if pre_domain_lines is not None else {}
        crawl_seen_fp = pre_seen_fp if pre_seen_fp is not None else set()
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)
        lines_to_check: List[str] = []

        # 1. 本地文件
        if Config.ENABLE_LOCAL_CHECK:
            input_path = str(Config.INPUT_FILE)
            self.logger.info(f"📂 读取本地: {input_path}")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    local_lines = [l.strip() for l in f if l.strip()]
                self.process_lines(local_lines, seen_fp, domain_lines)
            except Exception as e:
                self.logger.error(f"❌ 本地文件失败: {e}")

        # 2. 网络源
        if Config.ENABLE_WEB_CHECK:
            web_sources = Config.WEB_SOURCES or Config.PRESET_FILES
            if web_sources:
                self.logger.info(f"🌐 拉取 {len(web_sources)} 个网络源...")
                with ThreadPoolExecutor(max_workers=Config.FETCH_WORKERS) as executor:
                    future_to_url = {executor.submit(self.fetcher.fetch, url, Config.PROXY): url
                                     for url in web_sources}
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            fetched = future.result()
                            if fetched:
                                self.process_lines(fetched, seen_fp, domain_lines)
                        except Exception as e:
                            self.logger.error(f"❌ 拉取异常: {url} - {e}")

        # 3. 追加爬虫源（需要过滤）
        if crawl_domain_lines:
            for domain, urls in crawl_domain_lines.items():
                for url_line in urls:
                    parts = url_line.split(',', 1)
                    if len(parts) != 2:
                        continue
                    name, url = parts
                    # 过滤 VOD 域名
                    if URLCleaner.is_vod_domain(url):
                        continue
                    fp = URLCleaner.get_fingerprint(url)
                    if fp not in seen_fp and fp not in crawl_seen_fp:
                        seen_fp.add(fp)
                        domain_lines[domain].append(url_line)

        # 4. 收集待测源
        for urls in domain_lines.values():
            lines_to_check.extend(urls)

        if Config.MAX_SOURCES_TO_CHECK > 0:
            lines_to_check = lines_to_check[:Config.MAX_SOURCES_TO_CHECK]

        total = len(lines_to_check)
        if total == 0:
            self.logger.warning("⚠️ 没有可检测的源")
            return
        self.stats['total'] = total

        self.logger.info(f"📋 待测: {total} 条")

        cat_map: Dict[str, List[Dict]] = {c: [] for c in Config.CATEGORY_ORDER}
        fail_list: List[str] = []
        real_workers = min(args.workers, total)

        # 5. 并发测活（不用代理）
        with ThreadPoolExecutor(max_workers=real_workers) as executor, \
             tqdm(total=total, desc="检测", unit="条", ncols=70) as pbar:
            future_to_ln = {executor.submit(self.checker.check, ln, None): ln for ln in lines_to_check}
            done_count = 0
            for future in as_completed(future_to_ln):
                ln = future_to_ln[future]
                r = future.result()
                if r:
                    self.stats['valid'] += 1
                    fp = URLCleaner.get_fingerprint(r['url'])
                    self.cache.add(fp)
                    if r['overseas']:
                        self.stats['by_overseas']['overseas'] += 1
                    else:
                        self.stats['by_overseas']['cn'] += 1
                    if 'quality' not in r or r['quality'] == 0:
                        r['quality'] = Config.MIN_QUALITY_SCORE
                    category = NameProcessor.classify(r['name'])
                    if category in cat_map:
                        cat_map[category].append(r)
                else:
                    self.stats['failed'] += 1
                    fail_list.append(ln)
                done_count += 1
                pbar.update(1)

        # 6. 速度检测
        if Config.ENABLE_SPEED_CHECK:
            self.logger.info("⏳ 速度检测...")
            valid_sources = []
            for cat, chs in cat_map.items():
                for ch in chs:
                    valid_sources.append((cat, ch))
            speed_filtered = 0
            for cat, ch in tqdm(valid_sources, desc="测速", unit="条", ncols=60):
                speed = self.checker.check_speed(ch['url'], None)
                if speed < Config.MIN_SPEED_MBPS:
                    if ch in cat_map[cat]:
                        cat_map[cat].remove(ch)
                        speed_filtered += 1
                else:
                    ch['quality'] = min(ch['quality'] + int(speed * 10), 100)
            if speed_filtered > 0:
                self.stats['filtered_by_quality'] += speed_filtered

        # 7. 直连二验（不用代理）
        cat_map = self.direct_checker.filter_channels(cat_map)
        self.stats['valid'] = sum(len(v) for v in cat_map.values())

        # 8. 写入结果
        output_file = str(Config.OUTPUT_FILE)
        _total_written = self.write_results(output_file, cat_map, total, fail_list)

        # 9. 保存统计
        try:
            duration = time.time() - self.start_time
            self.stats_manager.update('total', total)
            self.stats_manager.update('valid', self.stats['valid'])
            self.stats_manager.update('failed', self.stats['failed'])
            self.stats_manager.update('filtered', self.stats['filtered_by_quality'])
            self.stats_manager.update('written', _total_written)
            self.stats_manager.update('duration_seconds', duration)
            self.cache.flush()  # 一次性原子写入缓存
            self.stats_manager.save()
            self.stats_manager.print_comparison()
        except Exception as e:
            self.logger.warning(f"⚠️ 统计保存失败: {e}")

    def write_results(self, output_file: str, cat_map: Dict[str, List[Dict]], total: int, fail_list: Optional[List[str]] = None) -> int:
        """写入结果文件"""
        output_limit = getattr(Config, 'MAX_OUTPUT_SOURCES', 2000)
        max_links = getattr(Config, 'MAX_LINKS_PER_NAME', 1)

        # 使用规范化名称进行分组，避免因名称差异导致重复
        cat_grouped: Dict[str, Dict[str, List[Dict]]] = {}
        for cat, channels in cat_map.items():
            grouped = defaultdict(list)
            for ch in channels:
                if Config.ENABLE_QUALITY_FILTER and ch.get('quality', 0) < Config.MIN_QUALITY_SCORE:
                    continue
                # 使用规范化名称作为分组键
                norm_name = NameProcessor.normalize(ch['name'])
                # 保存原始名称用于显示
                ch['_norm_name'] = norm_name
                grouped[norm_name].append(ch)
            if grouped:
                cat_grouped[cat] = grouped

        total_ch_count = sum(len(g) for g in cat_grouped.values())
        if total_ch_count == 0:
            self.logger.warning("⚠️ 无通过质量过滤的频道")
            return 0

        PRIORITY_CATS = [c for c in Config.CATEGORY_ORDER if c not in ("其他频道", "其他頻道")]
        PRIORITY_TOTAL = sum(len(cat_grouped.get(c, {})) for c in PRIORITY_CATS)
        OTHER_TOTAL = len(cat_grouped.get("其他频道", {})) + len(cat_grouped.get("其他頻道", {}))
        OTHER_QUOTA = max(30, (OTHER_TOTAL * output_limit // max(total_ch_count, 1)) if OTHER_TOTAL > 0 else 30)
        PRIORITY_QUOTA = max(0, output_limit - OTHER_QUOTA)

        cat_quota: Dict[str, int] = {}
        for cat in Config.CATEGORY_ORDER:
            if cat not in cat_grouped:
                continue
            ch_count = len(cat_grouped[cat])
            if cat in PRIORITY_CATS:
                cat_quota[cat] = (ch_count * PRIORITY_QUOTA // max(PRIORITY_TOTAL, 1))
            else:
                cat_quota[cat] = OTHER_QUOTA

        first_cat = next((c for c in Config.CATEGORY_ORDER if c in cat_quota), None)
        if first_cat:
            cat_quota[first_cat] += output_limit - sum(cat_quota.values())

        _total_written = 0
        try:
            _out = Path(output_file).resolve() if output_file else (Path(__file__).parent.parent / "live_ok.txt")
            _tmp = _out.with_suffix('.tmp.' + str(os.getpid()))

            with open(_tmp, 'w', encoding='utf-8') as f:
                for cat in Config.CATEGORY_ORDER:
                    if cat not in cat_grouped:
                        continue
                    grouped = cat_grouped[cat]
                    
                    # 判断是否为CCTV组（央视频道）
                    is_cctv_cat = '央视' in cat or '央視' in cat
                    
                    if is_cctv_cat:
                        # CCTV组：按固定顺序排列
                        def cctv_sort_key(norm_name):
                            # 从规范化名称提取CCTV编号
                            m = re.match(r'CCTV-?(\d+)(\+?)', norm_name, re.IGNORECASE)
                            if m:
                                num = int(m.group(1))
                                plus = 1 if m.group(2) else 0
                                # CCTV1-CCTV17 排在前面，CCTV5+ 紧跟CCTV5
                                if num == 5 and plus:
                                    return (5, 1)  # CCTV5+ 紧跟 CCTV5
                                return (num, 0)
                            # 非CCTV频道排在最后，按评分排序
                            return (999, -max(ch['quality'] for ch in grouped[norm_name]))
                        
                        ordered_keys = sorted(grouped.keys(), key=cctv_sort_key)
                    else:
                        # 其他组：按评分从高到低排序
                        ordered_keys = sorted(grouped.keys(),
                            key=lambda n: max(ch['quality'] for ch in grouped[n]), reverse=True)
                    
                    cat_count = 0
                    _wrote_genre = False
                    for norm_name in ordered_keys:
                        if _total_written >= output_limit:
                            break
                        if not _wrote_genre:
                            f.write(f"{cat},#genre#\n")
                            _wrote_genre = True
                        chs = sorted(grouped[norm_name], key=lambda x: x['quality'], reverse=True)
                        # 获取最佳显示名称
                        display_name = NameProcessor.get_display_name(chs[0]['name']) if chs else norm_name
                        for ch in chs[:max_links]:
                            if _total_written >= output_limit:
                                break
                            # 使用规范化后的显示名称
                            f.write(f"{display_name},{ch['url']}\n")
                            _total_written += 1
                            cat_count += 1
                    self.stats['by_category'][cat] = cat_count

            if _total_written > output_limit:
                _total_written = output_limit
            # 原子替换（同卷 .replace() 为原子操作，无"文件缺失"窗口）
            _tmp.replace(_out)
            self.logger.info(f"✅ 写入: {_out} ({_total_written} 条)")
        except Exception as e:
            self.logger.error(f"❌ 写入失败: {e}")
            backups = sorted(Config.BASE_DIR.glob('live_ok_backup_*.txt'), key=lambda p: p.stat().st_mtime, reverse=True)
            if backups:
                shutil.copy2(backups[0], _out)
                self.logger.info(f"🔄 从备份恢复: {backups[0].name}")

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"✅ 检测完成: 总计 {total} 条")
        self.logger.info(f"✅ 有效: {self.stats['valid']} | 失效: {self.stats['failed']}")
        self.logger.info(f"⚠️ 质量过滤: {self.stats['filtered_by_quality']} | 写入: {_total_written}")

        if Config.ARCHIVE_FAIL and fail_list:
            fail_file = _out.with_name(f"{_out.stem}_fail.txt")
            with open(fail_file, 'w', encoding='utf-8') as f:
                for line in fail_list:
                    f.write(f"{line}\n")
            self.logger.info(f"📦 失效源归档: {fail_file.name}")

        return _total_written

    async def run_async(self, args):
        """Async mode: crawl new sources, then merge into main check pipeline"""
        seen_fp: Set[str] = set()
        domain_lines: Dict[str, List[str]] = defaultdict(list)
        async_seen_fp: Set[str] = set()

        # 0. Async crawler: discover sub-playlist URLs from preset sources
        if getattr(args, 'async_crawl', False) or Config.ENABLE_ASYNC_CRAWL:
            web_sources = Config.WEB_SOURCES or Config.PRESET_FILES
            if web_sources:
                self.logger.info("? Async crawl mode: scanning %d preset sources...", len(web_sources))
                try:
                    async with AsyncWebSourceCrawler() as crawler:
                        raw_map: Dict[str, str] = await crawler.crawl_all()
                        self.logger.info("? Crawler found %d sub-URLs", len(raw_map))
                        for sub_url, base_domain in raw_map.items():
                            fp = URLCleaner.get_fingerprint(sub_url)
                            if fp in async_seen_fp:
                                continue
                            async_seen_fp.add(fp)
                            path_str = urlparse(sub_url).path
                            name = Path(path_str).stem
                            if name.isdigit() or len(name) <= 3:
                                name = base_domain
                            else:
                                name = "%s (%s)" % (name, base_domain)
                            domain_lines.setdefault("async_discovered", []).append("%s,%s" % (name, sub_url))
                except Exception as e:
                    self.logger.warning("! Async crawl error (non-fatal): %s", e)

        # 1. Sync fetch web_sources
        if Config.ENABLE_WEB_FETCH or getattr(args, 'async_crawl', False):
            web_sources = Config.WEB_SOURCES or Config.PRESET_FILES
            if web_sources:
                self.logger.info("? Fetching %d web sources...", len(web_sources))
                for url in web_sources:
                    try:
                        fetched = self.fetcher.fetch(url, Config.PROXY)
                        if fetched:
                            for ln in fetched:
                                if ',' not in ln:
                                    continue
                                name, stream_url = ln.split(',', 1)
                                if not name.strip() or not stream_url.strip().startswith('http'):
                                    continue
                                fp = URLCleaner.get_fingerprint(stream_url.strip())
                                if fp in seen_fp:
                                    continue
                                seen_fp.add(fp)
                                domain_lines.setdefault("crawled", []).append(ln)
                    except Exception as e:
                        self.logger.error("X Fetch error: %s - %s", url, e)

        self.run(args, pre_seen_fp=async_seen_fp, pre_domain_lines=domain_lines)