# async_crawler.py 逐行审查报告 + 改进方案
**审查时间：2026-04-30** | **文件：iptv_apex/crawler/async_crawler.py（262行）**

---

## 一、发现的问题（按严重程度）

### 🔴 严重问题

#### 1. `crawl_single_source_with_name` 行221-233：对txt格式的处理有bug
**问题**：txt格式（`name,url`）整行作为key放入dict，但后续`crawl_all()`取`url_to_name.update(r)`，导致key是整行字符串而非url，后续循环`for sub_url, base_domain in raw_map.items()`时`sub_url`会是整行如`"CCTV1,http://example.com"`，导致频道名和URL都错误。

```python
# 行227-230
if ',' in line:
    parts = line.split(',', 1)
    if len(parts) == 2 and parts[1].strip().startswith('http'):
        result[line] = base_domain   # ❌ key应该是URL，不是整行
        self.all_extracted.add(parts[1].strip())
```

**影响**：pipeline.py里 `f"{name},{sub_url}"` 会生成 `"CCTV1 (ghproxy.com),CCTV1,http://example.com"` 格式错误的行。

---

#### 2. `extract_sources_from_content` 行156-158：相同的key误用问题
**问题**：从txt内容中提取URL时，把整行（`name,url`）放入matches集合，但后面的`validate_and_add`接收的是URL字符串，这个URL实际上是从parts[1]来的，所以这里逻辑正确——但问题是matches里也可能混入整行字符串（不含http前缀），导致后续`validate_and_add`接受无效字符串。

```python
# 行156-158
if line.startswith(('http://', 'https://')) and ',' in line:
    all_matches.add(line.split(',', 1)[1].strip())  # ✅ 正确：提取url部分
elif line.startswith(('http://', 'https://')) and '.m3u' in line.lower():
    all_matches.add(line)  # ✅ 正确
```
**评估**：这部分逻辑本身正确，但注意行159的条件永远不会触发（因为`startswith('http')`已经覆盖了`.m3u`开头的行）。

---

### 🟡 中等问题

#### 3. `SOURCE_SITES` 属性使用 `PRESET_FILES`（空列表）在前
```python
@property
def SOURCE_SITES(self):
    return Config.PRESET_FILES if Config.PRESET_FILES else Config.WEB_SOURCES
```
`PRESET_FILES` 始终为空（已确认），所以实际使用的是 `WEB_SOURCES`。但 `WEB_SOURCES` 里的条目（比如`Guovin/iptv-api`输出、`dsj COS`、`iptv-org`等）本身就已经是频道列表（txt/m3u格式），异步爬虫把它们当成"页面"去提取子链接，意义有限。

**真正的价值**：从这些源的内容中**直接提取真实频道URL**（通过txt解析），而非提取子链接。

#### 4. `crawl_all()` 行254-256：没有去重
```python
for r in results:
    if isinstance(r, dict):
        url_to_name.update(r)  # update() 会覆盖同名key
```
这里应该用 `setdefault` 或检查是否存在，而不是无条件覆盖。

#### 5. 递归深度限制过严（行114、192）
- `extract_sources_from_content` 深度>1直接返回空（行115）
- 只取valid_sources前10个递归（行193）
- 对于多级嵌套的播放列表索引页（如包含多个子m3u链接），可能漏掉很多源

#### 6. `quick_validate` 行76-79：GET降级判断条件过宽
```python
if text.startswith('#EXTM3U') or 'm3u' in text.lower() or 'http' in text.lower():
    return True
```
`'http' in text.lower()` 会匹配任何包含"http"字样的页面（几乎所有网页），导致大量无效页面被误判为有效播放列表。

---

### 🟢 轻微问题

#### 7. `crawl_all()` 行249：使用print而非logging
```python
print("🔍 启动异步爬虫...")
```
项目统一使用logging，这里用print会导致日志丢失。

#### 8. 行108：文件名数字判断可能误杀
```python
if filename.isdigit() or len(filename) <= 10:
    return False
```
`len(filename) <= 10` 意味着文件名>10字符才通过。频道名如"CCTV5+体育.m3u8"（8字）会被拒绝。很多有意义的频道名短于10字。

#### 9. 行222条件判断：漏检部分txt格式
```python
if ',#genre#' in text or any(',' in line and line.startswith('http') == False for line in text.splitlines()[:10]):
```
这个条件过于复杂，`startswith('http') == False` = `not line.startswith('http')`，意味着"有逗号但不是http开头"——对于`name,url`格式，`name`部分确实不http开头，应该能匹配。但语义不清晰。

#### 10. 行184-189：分批处理顺序固定
```python
for i in range(0, len(matches_list), batch_size):
    await asyncio.gather(*[validate_and_add(s) for s in matches_list[i:i+batch_size]])
```
分批顺序执行而非全部并发，`batch_size=50` 且总任务数多时效率低。

---

## 二、当前代码与pipeline.py的集成分析

### 集成现状
- `pipeline.py` 的 `run_async()` 已修改为：先用 `AsyncWebSourceCrawler.crawl_all()` 发现URL，再用 `WebSourceFetcher` 同步拉取WEB_SOURCES，合并去重后传给主检测流程
- 但由于 `SOURCE_SITES = WEB_SOURCES`（9个订阅源），`crawl_all()` 对每个源执行 `quick_validate` → `extract_sources_from_content`，实际上是在把这9个源的内容当成"索引页"处理
- `extract_sources_from_content` 提取子URL（m3u/txt/live/stream/tv路径），而非直接提取频道URL

### 真正缺失的功能
**`run_async()` 里的异步爬虫目前没有从WEB_SOURCES内容中直接提取频道URL并加入测活池**。它只能发现"子播放列表链接"，但主测活流程已经有了WebSourceFetcher同步拉取这些URL的能力，async爬虫只是锦上添花。

---

## 三、改进方案

### 方案A：修复async_crawler的txt解析，让它成为真正的频道发现器

**核心改进**：让`crawl_all()`直接解析WEB_SOURCES内容中的频道行（`name,url`或`#EXTINF...http://...`），而非提取子链接。子链接发现作为补充。

```python
async def crawl_all(self) -> Dict[str, str]:
    """爬取所有预设源，直接提取频道URL（不去重，保留给pipeline做）"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("[AsyncCrawler] Starting crawl of %d sources...", len(self.SOURCE_SITES))
    semaphore = asyncio.Semaphore(10)
    
    async def process_source(url: str) -> Dict[str, str]:
        """返回 {url: domain}，直接从内容提取频道"""
        async with semaphore:
            try:
                parsed = urlparse(url)
                base_domain = parsed.netloc.split(':')[0]
                
                headers = {
                    'User-Agent': random.choice(Config.UA_POOL),
                    'Accept': '*/*',
                }
                resp = await self.session.get(url, headers=headers, timeout=15.0, follow_redirects=True)
                if resp.status_code != 200:
                    return {}
                
                text = resp.text
                result: Dict[str, str] = {}
                
                # 方式1：直接解析 txt 格式 (name,url)
                if ',' in text[:2000]:
                    for line in text.splitlines():
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if ',' in line:
                            parts = line.split(',', 1)
                            if len(parts) == 2 and parts[1].strip().startswith('http'):
                                url_part = parts[1].strip()
                                if url_part not in self.all_extracted:
                                    self.all_extracted.add(url_part)
                                    result[url_part] = base_domain
                
                # 方式2：解析 m3u 格式 (#EXTINF...http://)
                elif text.startswith('#EXTM3U') or '#EXTINF' in text[:2000]:
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith('#EXTINF'):
                            continue
                        if line.startswith('http'):
                            if line not in self.all_extracted:
                                self.all_extracted.add(line)
                                result[line] = base_domain
                
                # 方式3：纯URL列表（每行一个URL）
                else:
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith('http') and len(line) > 15:
                            if line not in self.all_extracted:
                                self.all_extracted.add(line)
                                result[line] = base_domain
                
                return result
                
            except Exception:
                return {}
    
    tasks = [process_source(url) for url in self.SOURCE_SITES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    url_to_name: Dict[str, str] = {}
    for r in results:
        if isinstance(r, dict):
            url_to_name.update(r)
    
    logger.info("[AsyncCrawler] Done: discovered %d channel URLs", len(url_to_name))
    return url_to_name
```

### 方案B：增强`pipeline.py`的`run_async()`，让它同时利用异步爬虫的快速验证能力

在测活阶段之前，用异步爬虫对所有候选URL做快速HEAD验证，过滤掉明显失效的URL，减少主测活线程压力。

### 方案C：添加新的高质量订阅源（当前最有效的改进）

从恩山论坛和搜索结果中发现的备选源，在加入config.json前先测活验证：

| 源 | URL | 预期质量 |
|----|-----|---------|
| HerbertHe/iptv-sources | raw content待探索 | 未知 |
| joevess/IPTV | gh-proxy镜像 | 高（gh-proxy可访问）|
| big-mouth-cn/tv | 已在config | 73.3% |
| 恩山论坛讨论的源 | 待抓取 | 待验证 |

---

## 四、推荐执行顺序

1. **立即修复**：行221的`result[line]`改为`result[parts[1].strip()]`（避免集成到pipeline后产生脏数据）
2. **短期**：实现方案A或方案B，让异步爬虫真正产出可测活的频道URL
3. **中期**：方案C，添加2-3个新的高质量订阅源
4. **长期**：优化递归深度、增加并发数、修复判断条件

---

*审查完成。代码整体结构合理，异步并发框架正确，主要问题集中在txt格式解析的key误用和验证条件过宽。*