# 📬 信息中转站（message_hub）

多来源消息统一聚合收件箱：IMAP 邮箱 / 一张网收件箱 / 庭审日程 / 前端手动上传，支持附件管理与下游自动化流转（如提交到法院短信流程）。

## 功能概述

- `MessageSource` 四种来源（imap / manual_upload / court_inbox / court_schedule）；IMAP 与手动上传在本 app，一张网适配器懒加载自 `plugins/message_hub/services/court/`
- IMAP 增量拉取：UID 水位增量 + SINCE 日期、发件人白/黑名单过滤（大小写不敏感子串）、附件落盘 `message_hub/imap/...`、正文截断 2000 字、IMAP 主机候选自动推断与回退（mail. / imap. 前缀互换）
- 前端材料预处理：多文件上传打包成「材料包」消息、追加附件、拆分草稿 `draft_state`（纯 UI 状态，语义由前端定义、后端仅存储）、重命名、硬删并清理物理文件
- 附件按需下载 + 预览（inline）、自定义下载名（custom_filename，自动补原扩展名，超长截断）
- Admin 提交到短信流程：从收件箱消息附件建 `CourtSMS`（正则提取案号）直接进入匹配阶段并派发 Q 任务
- OCR 框选取字端点：RapidOCR 识别页面图片返回归一化文字块坐标（供前端材料预处理拆分命名）
- 跨环境附件路径兼容：归一化 WSL `/mnt/d/...` 与 Windows `D:\...` 历史绝对路径，新数据统一存相对 MEDIA_ROOT 路径

## 目录结构

```
message_hub/
├── apps.py                # MessageHubConfig：ready() 注册定时任务
├── models/                # message_source / inbox_message
├── api/                   # inbox_api + message_source_api（组合 router）
├── schemas.py             # InboxMessageOut（含 draft_state 派生统计字段）
├── services/
│   ├── __init__.py        # get_fetcher 工厂
│   ├── base.py            # MessageFetcher 抽象 + 路径工具
│   ├── imap/imap_fetcher.py
│   ├── inbox_query.py / manual_upload_service.py
├── admin/                 # InboxMessageAdmin（552 行）+ MessageSourceAdmin
├── tasks.py               # 同步任务 + _register_schedule
├── static/ + templates/   # Admin 样式与附件面板模板
└── migrations/            # 0001–0013
```

## 数据模型

- `MessageSource` — 来源配置（凭证 FK、source_type、轮询间隔、sync_since、IMAP host/account、last_synced_uid、发件人白/黑名单、同步状态三态）
- `InboxMessage` — 统一消息（message_id 与 source 联合唯一去重、subject/sender/received_at、正文文本/HTML、附件元信息 JSON、draft_state、uploaded_by）

## API 端点

前缀 `/api/v1/inbox`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/messages` | 列表（按来源/类型/附件/关键词过滤） |
| GET/PUT/DELETE | `/messages/{id}` | 详情 / 重命名 / 清附件后硬删 |
| PUT | `/messages/{id}/draft` | 存草稿 |
| POST | `/messages/upload` | 多文件建材料包 |
| POST | `/messages/{id}/attachments` | 追加附件 |
| GET | `/messages/{id}/attachments/{part}/download`、`/preview` | 附件下载 / 预览 |
| POST | `.../rename` | 附件重命名 |
| POST | `/ocr` | RapidOCR 框选取字 |
| GET/POST | `/sources`、GET/PUT/DELETE `/sources/{id}` | 来源 CRUD |
| POST | `/sources/{id}/sync`、`/sources/sync-all` | 触发同步 |

## Admin

- `MessageSourceAdmin`：类型/同步状态徽章、立即同步按钮、发件人过滤折叠区
- `InboxMessageAdmin`：来源徽章、正文 iframe sandbox 预览、附件卡片式重命名面板、submit-to-sms 视图

## 异步任务与信号

- 定时任务 `message_hub:sync_all_sources`（**每 30 分钟**，`_register_schedule()` 经 apps.ready 注册——参照 `message_hub/tasks.py` 的注册模式，否则是死代码）；调度为每个启用来源提交独立 `sync_source_by_id` Q 任务避免串行阻塞
- 网络断开 / Playwright greenlet 等可预期错误自动降噪

## 外部集成

IMAP4_SSL 邮箱（凭证来自 organization.AccountCredential，密码 SecretCodec 解密）、RapidOCR、plugins 一张网收件箱/庭审日程（Playwright 类适配器）、automation CourtSMS 流程

## 依赖模块

- `apps.core`（tasking、异常、认证、storage_service）、`apps.organization`、`apps.automation`（仅 Admin 提交视图）、`plugins.message_hub`
