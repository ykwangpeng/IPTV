# IPTV 直播源聚合库

![IPTV](https://img.shields.io/badge/IPTV-Live%20Sources-blue) ![Python](https://img.shields.io/badge/Python-3.8+-green) ![License](https://img.shields.io/badge/License-MIT-orange)

> 📺 收录全球可用直播源，支持影视仓直接导入，开源免费，持续更新

---

## 📌 直接使用

### 影视仓 / TVBox / PIPTV 等播放器导入

**推荐直链（GitHub Raw）：**
```
https://raw.githubusercontent.com/litywang/IPTV/master/live_ok.txt
```

```
https://raw.githubusercontent.com/litywang/IPTV/master/live_ok.m3u
```

> 🔗 直接复制上方链接，粘贴到影视仓等播放器的「自建频道」或「直播源管理」处导入即可

---

## 📊 源库统计（最新）

| 指标 | 数据 |
|------|------|
| 可用源总数 | **1782+** |
| 频道分类 | 10 大类 |
| 数据格式 | `.txt` / `.m3u` |
| 更新方式 | GitHub Actions 自动更新（每日） |

---

## 📂 频道分类

| 分类 | 说明 | 典型频道 |
|------|------|----------|
| **4K 專區** | 2160P / 8K 超高清 | CCTV4K / 地方4K台 |
| **央視頻道** | CCTV 系列全频道 | CCTV1-17 / 中国教育 |
| **衛視綜藝** | 各省卫视综合频道 | 湖南/浙江/东方/北京... |
| **新聞資訊** | 新闻/财经/气象 | CCTV13 / 凤凰资讯 |
| **體育賽事** | 体育/足球/篮球/电竞 | CCTV5 / 咪咕 / 各大联赛 |
| **少兒動漫** | 少儿/卡通/动画 | 各大少儿频道 |
| **音樂頻道** | 音乐/MTV/演唱会 | 各大音乐频道 |
| **影視劇場** | 影视/电影/剧场 | 各大影视点播频道 |
| **港澳台國外** | 港台/海外精选 | TVB / 凤凰/ BBC / CNN |
| **其他頻道** | 未分类频道 | 全球其他直播源 |

---

## 🛠️ 使用检测工具

### 本地运行

```bash
# 克隆仓库
git clone https://github.com/litywang/IPTV.git
cd IPTV

# 安装依赖
pip install requests httpx zhconv tqdm

# 建议安装（可选，提升解析准确率）
pip install m3u8

# 运行检测（默认参数）
python IPTV-Apex-dzh.py

# 关闭速度检测（更快）
python IPTV-Apex-dzh.py --no-speed-check

# 启用异步爬虫 + 自定义并发
python IPTV-Apex-dzh.py --async-crawl -w 100

# 使用代理
python IPTV-Apex-dzh.py --proxy http://127.0.0.1:7890
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-i, --input` | paste.txt | 输入文件路径 |
| `-o, --output` | live_ok.txt | 输出文件路径 |
| `-w, --workers` | 120 | 并发检测线程数 |
| `-t, --timeout` | 15 | 境内源超时（秒） |
| `--proxy` | 无 | 代理地址 |
| `--no-speed-check` | 关闭 | 关闭速度检测（提速） |
| `--no-cache` | 关闭 | 禁用URL去重缓存 |
| `--async-crawl` | 关闭 | 启用异步爬虫扫描新源 |

---

## ⚙️ 配置文件说明

运行后自动生成 `config.json`，关键配置项：

```json
{
  "ENABLE_WEB_CHECK": true,
  "ENABLE_WEB_FETCH": true,
  "ENABLE_SPEED_CHECK": false,
  "ENABLE_CACHE": false,
  "SKIP_WEB_VALIDATE": true,
  "MAX_SOURCES_TO_CHECK": 15000,
  "MAX_OUTPUT_SOURCES": 2500,
  "MAX_WORKERS": 120,
  "TIMEOUT_CN": 15,
  "TIMEOUT_OVERSEAS": 30,
  "RETRY_COUNT": 2,
  "MIN_QUALITY_SCORE": 5,
  "web_sources": [
    "https://iptv-org.github.io/iptv/index.m3u",
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt"
  ]
}
```

### 关键配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SKIP_WEB_VALIDATE` | `true` | 跳过预置源 HTTP 验证（解决美国服务器境内源超时） |
| `MAX_SOURCES_TO_CHECK` | `15000` | 待检测源数量上限 |
| `MAX_OUTPUT_SOURCES` | `2500` | 最终输出源数量上限 |
| `ENABLE_CACHE` | `false` | URL 去重缓存（关闭以检测所有源） |

---

## 🔧 工具功能特性

| 优化项 | 说明 |
|--------|------|
| M3U8 解析增强 | 支持 m3u8 库，频道名解析准确率提升 10-20% |
| 轻量级缓存 | URL 去重缓存（TTL 24小时），避免重复检测 |
| ffprobe 优化 | probesize 5M / analyzeduration 10M，降低误判率 |
| 分辨率过滤 | 自动过滤低于 640x480 的低质量源 |
| 爬虫质量控制 | 域名白名单/黑名单评分机制 |
| 统计持久化 | JSON 文件记录历史运行数据 |
| 点播域名过滤 | 覆盖百度/抖音/快手/淘宝等短视频 CDN |
| IPv6 优化 | IPv6 源延迟加权评分 |

---

## 🤖 GitHub Actions 自动更新

本仓库配置了 GitHub Actions，每天自动运行检测并更新 `live_ok.txt`。

> ⚠️ **注意**: Actions 运行在 Linux 环境，如需 ffprobe 支持，请在 workflow 中添加：
> ```yaml
> - name: Install FFmpeg
>   run: sudo apt-get update && sudo apt-get install -y ffmpeg
> ```

---

## 📦 依赖说明

| 依赖 | 必需 | 说明 |
|------|------|------|
| requests | ✅ | HTTP 请求 |
| httpx | ✅ | 异步 HTTP |
| zhconv | ✅ | 繁简转换 |
| tqdm | ✅ | 进度条 |
| m3u8 | ✅ | M3U8 解析（推荐安装） |
| ffprobe | ✅ | 流检测（推荐安装，Actions 已自动安装） |

---

## 📝 文件说明

| 文件 | 说明 |
|------|------|
| `live_ok.txt` | 可用直播源列表（名称,URL 格式） |
| `live_ok.m3u` | M3U8 格式可直接导入播放器 |
| `IPTV-Apex-dzh.py` | 检测主脚本 |
| `config.json` | 配置文件 |
| `paste.txt` | 本地待检测源列表 |

---

## 🙏 致谢

- 基于 [IPTV-Apex-Lity](https://github.com/litywang/IPTV) 开发
- 参考 [IPTV-Apex](https://github.com/CoiaPrant/IPTV-Apex)
- 参考 [Guovin/iptv-api](https://github.com/Guovin/iptv-api)
- 参考 [fanmingming/live](https://github.com/fanmingming/live)
- 数据源 [iptv-org](https://github.com/iptv-org/iptv)

## License

MIT License
