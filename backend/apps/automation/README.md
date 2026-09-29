# 🤖 自动化工具（automation）

自动化工具集：法院短信全闭环处理、法院文书爬虫下载框架、法院 Token 管理、财产保全担保费询价、一张网在线立案/担保、GSXT 企业信用报告爬取、OCR 引擎层与多平台聊天 Provider。

> **拆分历史**：图片旋转（image_rotation）、发票识别（invoice_recognition）、文书识别（document_recognition）、文档解析（document_parsing）、PDF 拆解（pdf_splitting）、批量打印（batch_printing）、故事可视化（story_viz）、劳动仲裁爬虫（labor_arbitration）、快递查询（express_query）等已从本 app 拆分为独立 app；login / token / captcha / preservation_quote 等能力已插件化到 `plugins/court_automation`（本 app 内留 stub 转发）。

## 功能概述

- **法院短信全闭环**：解析 → 下载 → 案件匹配 → 重命名 → 多平台通知 → 归档，含 SHA-256 去重、任务恢复（`recover_court_sms_tasks` 命令）、中止并删除、人工指定案件、剪贴板复制/打包下载
- **法院文书爬虫框架**：多法院站点适配（一张网 zxfw、送达网 sfdw、广东 gdems、湖北 hbfy、江西 jxfy、揭阳 jysd、道律司法送达 daolv）
- **财产保全担保费询价**：模型层在本 app（PreservationQuote/InsuranceQuote/CasePreservationQuoteBinding），服务/Admin/API 在 `plugins/court_automation/preservation_quote`，router 挂在 automation 前缀下
- **一张网在线立案/担保**：`plugins/court_automation/filing|guarantee`，独立前缀 `/api/v1/court-filing`、`/api/v1/court-guarantee`
- **GSXT 企业信用报告爬取**：邮件收取 / 登录 / 逆向登录三条链路
- **OCR 引擎层**：RapidOCR / PaddleOCR API / Mac Vision / PDF 文本抽取（`services/ocr/`，被多个 app 复用）
- **多平台聊天 Provider**：飞书 / 钉钉 / 企业微信 / Telegram（`services/chat/` + `integrations/chat/message_sender.py`）
- **AI 文档处理与自动命名**（document_processor / auto_namer）、验证码识别（手动 + captcha_ocr 插件）、诉讼文书信号提取（`services/litigation/`，供 litigation_ai）
- 性能监控 API（`/automation/performance/*`）

## 目录结构

```
automation/
├── api/            # 7 个路由文件：main_api、court_sms_api、document_processor_api、
│                   #   auto_namer_api、captcha_recognition_api、captcha_manual_api、performance_monitor_api
├── admin/          # document/、scraper/、sms/、token/(stub)、tools_hub_admin
├── integrations/chat/message_sender.py   # ChatMessageSender Protocol + Provider 适配
├── management/commands/  # bench_http、clear_token_cache、download_ocr_models、
│                         #   optimize_token_performance、process_pending_tasks、
│                         #   recover_court_sms_tasks、smoke_check
├── models/         # base、court_document、court_sms、gsxt_report、invoice_recognition、
│                   #   preservation、scraper、token
├── schemas/        # captcha、court_document、court_sms、document、performance
├── services/
│   ├── sms/        # 法院短信闭环核心（解析/匹配/重命名/去重/恢复/归档/通知 + stages/ 阶段处理器）
│   ├── scraper/    # core/(cookie/token/monitor/security...) + scrapers/(8 站点) + sites/(一张网+担保)
│   ├── ocr/        # OCR 引擎（adapter、mac_vision、paddleocr_api、pdf_text_extractor）
│   ├── gsxt/       # 企业信用报告（登录、邮件收取、逆向登录）
│   ├── chat/       # 多平台聊天 Provider + factory
│   ├── ai/         # AI 工具服务与提示词
│   ├── document/、litigation/、captcha/(stub)、token/(stub)
│   ├── config_service.py、wiring.py
├── tasks/          # scraping_tasks（爬虫任务执行/卡死检查/询价）、gsxt_tasks
├── usecases/       # court_sms/（process、retry_download、submission）、token/auto_login
├── workers/        # court_sms_tasks（Django-Q 异步任务入口）
├── utils/、signals.py（文件清理）、checks.py（系统检查）、dtos.py、exceptions.py
```

## 数据模型

| 模型 | 说明 |
|------|------|
| `AutomationTool` / `NamerTool` / `TestCourt` / `TestToolsHub` | 虚拟模型，Admin 入口 |
| `CourtToken` / `TokenAcquisitionHistory` | 法院 Token（服务/Admin 在 plugins/court_automation） |
| `ScraperTask` | 爬虫任务（LifecycleModel） |
| `CourtDocument` | 法院文书 |
| `CourtSMS` | 法院短信（状态机 10 态，含 filing_notification 类型） |
| `PreservationQuote` / `InsuranceQuote` / `CasePreservationQuoteBinding` | 保全询价（服务在 plugins） |
| `InvoiceRecognitionTask` / `InvoiceRecord` | 发票（表归本 app，invoice_recognition app 用 managed=False 镜像） |
| `GsxtReportTask` | 企业信用报告任务 |

## API 端点

前缀 `/api/v1/automation`（JWTOrSessionAuth；captcha 两个端点 auth=None）：

| 端点组 | 说明 |
|--------|------|
| `/court-sms` | POST 提交（含 `/form`）、GET 列表/详情、`/assign-case`、`/retry`、`/batch-delete`、`/abort-and-delete`、`/documents/{id}/download|rename`、`/documents/copy-to-clipboard`、`/documents/download-all` |
| `/document-processor` | `process` / `process-by-path` |
| `/auto-namer` | `process` / `process-by-path` |
| `/captcha` | `recognize`（auth=None）、`manual/{task_id}/image|answer`（auth=None） |
| `/file/upload`、`/config`、`/status` | AI 工具（main_api） |
| `/performance/*` | metrics、statistics、health、cache 等性能监控 |
| `/preservation-quotes*` | 询价 CRUD + `/{id}/execute`、`/{id}/retry`（plugin router 挂本前缀下） |

另有 `/api/v1/court-filing`、`/api/v1/court-guarantee`（plugins.court_automation.filing|guarantee）。

## 浏览器自动化规范

**禁止直接使用 `sync_playwright()` / `async_playwright()`**，必须走 `apps.core.services.browser` 公共服务（create_browser / create_browser_async，Profile 体系含一张网反检测）。历史 README 中的 `BrowserManager` / `BrowserConfig` 已不存在。

## 通知渠道

法院短信等通知经 `ServiceLocator.get_case_chat_service()` 走多平台 ChatProvider（飞书/钉钉/企业微信/Telegram），不是单一直推 webhook。

## 测试

```bash
cd backend
env -u PYTHONHOME -u PYTHONPATH DB_NAME=test_fachuan_dev \
  .venv/bin/pytest tests/ci/unit/automation/ -q --reuse-db --timeout=900
```

## 依赖模块

- `apps.core`（ServiceLocator、tasking、browser、LLM、OCR 协议）
- `plugins/court_automation`（login、token、captcha、preservation_quote、filing、guarantee）
