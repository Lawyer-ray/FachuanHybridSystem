# 劳动仲裁文书爬虫（labor_arbitration）

爬取佛山市人社局「劳动仲裁文书公开」6 个区县的全部仲裁裁决书，入库并支持调用文档解析服务做 OCR。

## 一、运行机制

爬虫为**纯 HTTP 版**（`services/crawler.py`），不依赖浏览器 / Playwright：

| 阶段 | 做法 |
|---|---|
| 列表 | 调接口 `POST https://hrss.foshan.gov.cn/postmeta/i/{category_id}.json`，**一次返回最多 2500 篇**（`title`/`url`/`date`/`publish_time`），无需 cookie、翻页、浏览器 |
| 详情 | `requests` 抓详情页 HTML，正则提取扫描件图片 URL（`img/.../post_N.png`），**只存 URL、不下载图片** |
| 增量 | 已存在 `detail_url` 且 `success` 且有图 → 跳过；`failed` / 无图 → 自动重试 |
| 容错 | 列表接口 / 详情页请求带有限重试；失败标记 `failed`，由增量爬取 / 重试按钮兜底 |

**任务入口**：走 Django-Q 后台任务（`tasks.crawl_source`），经 `apps.core.tasking.submit_task` 入队；网络中断恢复依赖 Django-Q 内置 `retry`（20 分钟 × 3 次）+ 爬虫内 `goto` 重试。

## 二、数据模型

- `ArbitrationDocumentSource`：来源（6 区县），字段 `name`/`district`/`list_url`(unique)/`category_id`/`enabled`/`last_crawl_status` 等；`trigger_update()` 提交增量爬取任务（防重入：RUNNING 时跳过）。
- `ArbitrationDocument`：文书，`detail_url`(unique)/`title`/`case_number`/`publish_date`/`publish_datetime`/`crawl_status`/`parse_status`/`parsed_text` 等；`trigger_parse()` / `trigger_recrawl()`。
- `ArbitrationDocumentImage`：文书图片，`source_url`（原图 URL，`image` 字段已改可空、不落盘）/`page_index` 等。

## 三、如何启动

### 1. 前置：Django-Q worker 必须运行

```bash
cd backend
make qcluster-dev            # 或 .venv/bin/python apiSystem/manage.py qcluster
```

### 2. 写入 6 个来源（幂等）

```bash
.venv/bin/python apiSystem/manage.py seed_labor_arbitration_sources
```

### 3. 爬取

```bash
# 全量爬取
.venv/bin/python apiSystem/manage.py crawl_labor_arbitration --all
# 单来源 / 试跑
.venv/bin/python apiSystem/manage.py crawl_labor_arbitration --source 2 --limit 20
```

### 4. 清理误抓的导航页（历史遗留，按需）

```bash
.venv/bin/python apiSystem/manage.py purge_labor_arbitration_nav --dry-run   # 先预览
.venv/bin/python apiSystem/manage.py purge_labor_arbitration_nav            # 实际删除
```

### 5. Admin 操作

- 来源列表 `/admin/labor_arbitration/arbitrationdocumentsource/`：点「增量更新」触发爬取。
- 文书列表 `/admin/labor_arbitration/arbitrationdocument/`：「调用文档解析」（OCR）、「重试抓取图片」（下拉菜单批量动作）。

## 四、6 区来源映射

| 区县 | `list_url` 目录 | `category_id` |
|---|---|---|
| 市直 | `szzcws/` | 42087 |
| 禅城 | `ccqzcws/` | 41998 |
| 南海 | `nhqzcws/` | 41999 |
| 顺德 | `sdqzcws/` | 42000 |
| 高明 | `gmqzcws/` | 42001 |
| 三水 | `ssqzcws/` | 42002 |

## 五、文档解析（OCR）

`services/parsing_service.py` 调用项目 `document_parsing` 服务入口 `get_document_parser(backend=...)`，解析时从 `source_url` 下载到临时文件再 OCR，用后清理；逐页拼接 text/markdown 写回 `ArbitrationDocument`。

## 六、已知限制

1. **站点 2500 篇上限（无法绕过）**：站点 `pages_limit=50`（接口与 HTML 一致），单区最多拿最新 **2500** 篇。南海（21140）/ 顺德（12667）/ 禅城（3666）超过部分拿不到；市直（88）/ 高明（978）/ 三水（2323）可拿全。
2. **网络不稳定**：佛山站点偶发详情页 `goto` 超时，已加爬虫内重试 + Django-Q `retry` 兜底，极端情况下仍会少量 `failed`（可经「重试抓取」动作补）。
3. **worker 需加载新版代码**：纯 HTTP 版必须生效（几十篇/秒）；若 worker 因热重载滞后仍在跑旧 Playwright 代码（几篇/秒 + 下载图片），需重启 worker。
