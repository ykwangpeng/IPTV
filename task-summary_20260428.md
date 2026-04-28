# IPTV-Apex 模块化重构完成

## 目标
将单文件 `IPTV-Apex-dzh.py`（~2060行）重构为模块化结构，提升可维护性。

## 核心原则
- **输出频道在中国大陆能播放**
- **订阅拉取可用代理，频道测活不用代理**
- `live_ok.m3u` → GitHub, `live_ok.txt` → GitHub + GIST

## 新目录结构
```
C:\tools\IPTV\
├── iptv_apex\              # 主包
│   ├── __init__.py
│   ├── config.py            # 配置管理（支持 config.json 覆盖）
│   ├── utils\               # 工具模块
│   │   ├── url.py           # URLCache, URLCleaner
│   │   ├── name.py          # NameProcessor
│   │   └── stats.py         # StatsManager
│   ├── crawler\             # 爬虫模块
│   │   ├── sync_fetcher.py  # WebSourceFetcher（同步）
│   │   └── async_crawler.py # AsyncWebSourceCrawler（异步）
│   ├── checker\             # 检测模块
│   │   ├── stream.py        # StreamChecker（测活）
│   │   ├── resolution.py    # ResolutionDetector
│   │   └── direct.py        # DirectChecker（直连二验）
│   └── core\                # 核心流程
│       ├── parser.py        # M3UParser
│       └── pipeline.py      # IPTVChecker（主流程）
├── scripts\                 # 原有脚本
│   ├── generate_m3u.py
│   └── sync_to_gist.py
├── config.json              # 迁移出的配置（订阅源、分类规则、过滤列表）
├── run_iptv.py              # 新入口脚本
├── run_iptv.bat             # 更新为调用 run_iptv.py
└── IPTV-Apex-dzh.py         # 原文件保留备份
```

## 关键变更
1. **配置外置**：`PRESET_FILES`、`CATEGORY_RULES`、`VOD_DOMAINS`、`BLACKLIST` 等迁移至 `config.json`
2. **代理策略不变**：
   - `crawler/` 模块可用代理（`Config.PROXY`）
   - `checker/` 模块测活不用代理
   - `direct.py` 直连二验强制 `proxies=None`
3. **向后兼容**：`run_iptv.bat` 调用新入口，原单文件保留
4. **编码修复**：Windows 下强制 `utf-8` 输出，避免中文乱码

## 验证结果
- 语法检查通过（`py_compile` 全部通过）
- 配置加载正常（`Config.load_from_file()` + `init_compiled_rules()`）
- 分类规则编译正确（10 个分类全部识别）
- 主流程可正常启动（检测到 2455 条本地源，进度条正常）

## 待办
- [ ] 完整运行一次验证输出文件格式
- [ ] 确认 `generate_m3u.py` 和 `sync_to_gist.py` 兼容新输出
- [ ] 删除原 `IPTV-Apex-dzh.py` 或保留为备份
