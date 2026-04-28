#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 IPTV 项目中的 5 个 bug"""

import sys

def fix_main_entry_point():
    """Bug 1: 追加入口点到 IPTV-Apex-dzh.py 末尾"""
    path = r"C:\tools\IPTV\IPTV-Apex-dzh.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if 'if __name__ == "__main__"' in content:
        print("[SKIP] Bug1: 入口点已存在")
        return
    # 找 IPTVChecker 类里的 run 方法，用它构造入口点
    # 直接追加标准 argparse + main() 调用
    append = """

# ==================== 命令行入口 ====================
def main():
    parser = argparse.ArgumentParser(description="IPTV-Apex-dzh 直播源检测")
    parser.add_argument('-w', '--workers', type=int, default=80, help='并发线程数 (默认 80)')
    parser.add_argument('-t', '--timeout', type=int, default=8, help='单源超时秒数 (默认 8)')
    parser.add_argument('--no-local', action='store_true', help='跳过本地 paste.txt')
    parser.add_argument('--no-web-fetch', action='store_true', help='跳过网络爬取')
    parser.add_argument('--no-speed-check', action='store_true', help='关闭速度检测')
    parser.add_argument('--incremental', action='store_true', help='增量模式（仅检测新源）')
    args = parser.parse_args()

    checker = IPTVChecker()
   .Config.ENABLE_WEB_FETCH = not args.no_web_fetch
    if args.no_local:
        Config.INPUT_FILE = None
    if args.no_speed_check:
        Config.ENABLE_SPEED_CHECK = False
    if args.incremental:
        # 增量模式：只处理爬虫新源
        checker.run_async(args)
    else:
        checker.run(args)

if __name__ == '__main__':
    main()
"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(append)
    print("[OK] Bug1: 入口点已追加")

def fix_urllib3_warning():
    """Bug 2: 将 warnings.filterwarnings 移到 import requests 之前"""
    path = r"C:\tools\IPTV\IPTV-Apex-dzh.py"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 找到 import requests 行和 warnings.filterwarnings 行
    import_line = None
    warning_line = None
    for i, line in enumerate(lines):
        if line.startswith("import requests") or line.strip() == "import requests":
            import_line = i
        if "warnings.filterwarnings" in line and "Unverified" in line:
            warning_line = i

    if import_line is None:
        print("[SKIP] Bug2: 未找到 import requests")
        return
    if warning_line is None:
        print("[SKIP] Bug2: 未找到 warnings.filterwarnings")
        return

    if warning_line > import_line:
        # 需要把 warning_line 的内容移到 import_line 之前
        warning_text = lines[warning_line]
        # 删除原 warning 行
        del lines[warning_line]
        # 在 import requests 前插入
        new_import_line = import_line if warning_line > import_line else import_line - 1
        lines.insert(new_import_line, warning_text)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[OK] Bug2: urllib3 警告已移到 import requests 之前")
    else:
        print("[SKIP] Bug2: 警告已在 import 之前")

def fix_ghp_match():
    """Bug 3: sync_to_gist.py 第67行 'ghp_' 匹配过于宽泛"""
    path = r"C:\tools\IPTV\scripts\sync_to_gist.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    old = "        if 'ghp_' in line:"
    new = "        if line.startswith('user.ghp_') or line.startswith('github.token=') or (line.startswith('user.') and 'ghp_' in line):"
    if old in content:
        content = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] Bug3: ghp_ 匹配已收紧")
    else:
        print("[SKIP] Bug3: 未找到目标代码")

def fix_hardcoded_gist_id():
    """Bug 4: sync_to_gist.py 硬编码 GIST_ID 默认值"""
    path = r"C:\tools\IPTV\scripts\sync_to_gist.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    old = "gist_id = os.environ.get('GIST_ID', 'dc272a4f2e95ffbd41e7e31d27ef3d76')"
    new = "gist_id = os.environ.get('GIST_ID', '')"
    if old in content:
        content = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] Bug4: 硬编码 GIST_ID 已移除（必须通过环境变量设置）")
    else:
        print("[SKIP] Bug4: 未找到目标代码")

def fix_etag_conditional_request():
    """Bug 5: iptv_monitor.py 添加 ETag 条件请求支持"""
    path = r"C:\tools\IPTV\iptv_monitor.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "If-None-Match" in content:
        print("[SKIP] Bug5: ETag 条件请求已存在")
        return
    # 在 fetch_source 函数中添加 headers 中的 If-None-Match
    old_fetch = '''def fetch_source(url: str, timeout: int = 30) -> tuple:
    """拉取源内容，返回 (content_str, etag_or_None)"""
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    headers = {"User-Agent": "Mozilla/5.0 IPTV-Monitor/1.0"}
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
        resp.raise_for_status()
        etag = resp.headers.get("ETag")
        return resp.text, etag
    except Exception as e:
        log.warning(f"  下载失败 {url}: {e}")
        return None, None'''
    
    new_fetch = '''def fetch_source(url: str, timeout: int = 30, etag: str = None) -> tuple:
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
        return None, None, False'''
    
    if old_fetch in content:
        content = content.replace(old_fetch, new_fetch, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] Bug5: fetch_source 已支持 ETag 条件请求")
    else:
        print("[SKIP] Bug5: 未找到目标代码（可能已修改）")

if __name__ == "__main__":
    print("=== IPTV Bug 修复脚本 ===")
    fix_main_entry_point()
    fix_urllib3_warning()
    fix_ghp_match()
    fix_hardcoded_gist_id()
    fix_etag_conditional_request()
    print("=== 完成 ===")
