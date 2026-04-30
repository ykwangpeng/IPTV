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


def load_config_sources(base_dir: Path) -> dict:
    """从 config.json 加载 web_sources 作为监控源（去重，保留顺序）"""
    config_file = base_dir / "config.json"
    sources = {}
    seen_urls = set()
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 只读 web_sources（preset_files 已合并到 web_sources）
            src_cfg = data.get("sources", {})
            url_list = src_cfg.get("web_sources", [])
            for url in url_list:
                if not url.startswith(("http://", "https://")):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                # 用域名+路径最后一段作为短名
                parsed = urlparse(url)
                path_part = parsed.path.strip("/").split("/")[-1] if parsed.path else ""
                short_name = f"{parsed.netloc}/{path_part}" if path_part else parsed.netloc
                # 去重：同名加序号
                orig = short_name
                idx = 1
                while short_name in sources:
                    short_name = f"{orig}#{idx}"
                    idx += 1
                sources[short_name] = url
        except Exception as e:
            log.warning(f"加载 config.json 失败: {e}")
    return sources

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

# ── 订阅源列表（从 config.json 加载，失败则回退到内置列表）──
DEFAULT_SOURCES = {
    "live.zbds.top":       "https://live.zbds.top/tv/iptv4.m3u",
    "live.hacks zho":      "https://live.hacks.tools/iptv/languages/zho.m3u",
    "live.hacks Taiwan":   "https://live.hacks.tools/tv/ipv4/categories/taiwan.m3u",
    "live.hacks Movies":   "https://live.hacks.tools/tv/ipv4/categories/%E7%94%B5%E5%BD%B1%E9%A2%91%E9%81%93.m3u",
    "dsj COS":             "https://dsj-1312694395.cos.ap-guangzhou.myqcloud.com/dsj10.1.txt",
    "live.hacks Macau":    "https://live.hacks.tools/tv/ipv4/categories/macau.m3u",
    "live.hacks HongKong": "https://live.hacks.tools/tv/ipv4/categories/hong_kong.m3u",
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

    # 优先从 config.json 加载源列表
    SOURCES = load_config_sources(BASE_DIR)
    if not SOURCES:
        log.warning("config.json 无有效源，使用内置默认列表")
        SOURCES = DEFAULT_SOURCES
    log.info(f"监控源数量: {len(SOURCES)}")

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

        # 触发增量更新（后台异步执行，不阻塞监控）
        log.info("=== 触发增量更新 ===")
        apex_script = BASE_DIR / "run_iptv.py"
        if apex_script.exists():
            try:
                import subprocess
                # 使用 Popen 后台启动，避免阻塞监控进程
                subprocess.Popen(
                    [sys.executable, str(apex_script), "--incremental", "--no-speed-check", "-w", "40"],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0,
                )
                log.info("[OK] 增量更新已后台启动")
            except Exception as e:
                log.error(f"[FAIL] 增量更新启动异常: {e}")
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
