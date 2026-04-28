# -*- coding: utf-8 -*-
"""
IPTV RSS Monitor - 检测订阅源变化
比较各源的 MD5 哈希值，发现变化时写入 .source_changed.json 和 .bw_trigger
"""
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import requests

# ── 基本设置 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
HASH_FILE = BASE_DIR / ".source_hashes.json"
CHANGED_FILE = BASE_DIR / ".source_changed.json"
TRIGGER_FILE = BASE_DIR / ".bw_trigger"
LOG_FILE = BASE_DIR / "monitor.log"

# 代理配置（从环境变量读取）
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None

# ── 日志 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iptv_monitor")

# ── 订阅源列表（短名 → URL）───────────────────────────────
SOURCES = {
    "FYTV":                "http://iptv.4666888.xyz/FYTV.m3u",
    "xinzb":               "http://47.120.41.246:8899/xinzb.txt",
    "live.zbds.top":       "https://live.zbds.top/tv/iptv4.m3u",
    "live.hacks zho":      "https://live.hacks.tools/iptv/languages/zho.m3u",
    "live.hacks Taiwan":   "https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u",
    "live.hacks Movies":   "https://live.hacks.tools/tv/ipv4/categories/%E7%94%B5%E5%BD%B1%E9%A2%91%E9%81%93.m3u",
    "dsj COS":             "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
    "live.hacks Macau":    "https://live.hacks.tools/tv/ipv4/categories/macau.m3u",
    "live.hacks HongKong": "https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u",
    "zxmlxw520 GitHub":    "https://raw.githubusercontent.com/zxmlxw520/5566/refs/heads/main/fhtv.txt",
    "peterhchina GitHub":  "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
    "imDazui GitHub":      "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8202506.m3u",
    "iptv-org Taiwan":     "https://iptv-org.github.io/iptv/countries/tw.m3u",
}


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def fetch_source(url: str, timeout: int = 30, etag: str = None) -> tuple:
    """拉取源内容，返回 (content_str, etag_or_None, changed_bool)"""
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    headers = {"User-Agent": "Mozilla/5.0 IPTV-Monitor/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        resp.raise_for_status()
        new_etag = resp.headers.get("ETag")
        if resp.status_code == 304:
            return None, new_etag, False
        return resp.text, new_etag, True
    except Exception as e:
        log.warning(f"  下载失败 {url}: {e}")
        return None, None, False


def load_hashes() -> dict:
    if HASH_FILE.exists():
        try:
            with open(HASH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_hashes(data: dict):
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    log.info("=== IPTV RSS Monitor scan start ===")

    old_hashes = load_hashes()
    new_hashes = {}
    changed = []

    for short_name, url in SOURCES.items():
        old_etag_str = old_hashes.get(url + ".__etag")
        content, etag, _changed = fetch_source(url, etag=old_etag_str)
        if content is None:
            # 下载失败或 304 Not Modified，保留旧哈希
            if url in old_hashes:
                new_hashes[url] = old_hashes[url]
            continue

        new_hash = md5(content)
        new_hashes[url] = new_hash

        old_hash = old_hashes.get(url)
        old_etag_str = old_hashes.get(url + ".__etag")

        if old_hash and old_hash != new_hash:
            log.info(
                f"[{short_name}] CHANGED "
                f"(hash: {old_hash[:12]} -> {new_hash[:12]}, "
                f'etag: {old_etag_str or "None"} -> {etag or "None"})'
            )
            changed.append({
                "name": short_name,
                "url": url,
                "old_hash": old_hash,
                "new_hash": new_hash,
                "old_etag": old_etag_str,
                "new_etag": etag,
            })
        # 记录 etag
        new_hashes[url + ".__etag"] = etag

    if changed:
        log.info(f"Changed sources: {len(changed)}")
        # 写变化详情
        with open(CHANGED_FILE, "w", encoding="utf-8") as f:
            json.dump(changed, f, indent=2, ensure_ascii=False)
        log.info(f"Trigger file written: {CHANGED_FILE} ({len(changed)} sources)")

        # 写触发标记
        TRIGGER_FILE.write_text("1", encoding="utf-8")
        log.info(f"Trigger flag created: {TRIGGER_FILE}")

        # 触发增量更新
        log.info("=== 触发增量更新 ===")
        apex_script = BASE_DIR / "IPTV-Apex-dzh.py"
        if apex_script.exists():
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(apex_script), "--incremental"],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                )
                if result.returncode == 0:
                    log.info("[OK] 增量更新成功")
                else:
                    log.error(f"[FAIL] 增量更新失败 (rc={result.returncode})")
                    if result.stderr:
                        log.error(result.stderr[:500])
            except subprocess.TimeoutExpired:
                log.error("[FAIL] 增量更新超时")
            except Exception as e:
                log.error(f"[FAIL] 增量更新异常: {e}")
        else:
            log.warning(f"主脚本不存在: {apex_script}")

        print("CHANGES")
    else:
        log.info("NO_CHANGES: 所有订阅源无变化")
        print("NO_CHANGES")

    # 保存新哈希
    save_hashes(new_hashes)
    log.info("=== IPTV RSS Monitor scan done ===")


if __name__ == "__main__":
    main()
