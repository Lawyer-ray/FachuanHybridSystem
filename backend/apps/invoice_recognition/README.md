# 🧾 发票识别（invoice_recognition）

发票文件（PDF/图片）批量上传 → OCR/文本层提取 → 正则解析结构化字段 → 去重与按类目分组统计 → 按类目合并 PDF / 打包 ZIP 下载。从 automation 拆分的独立 app。

## 功能概述

- 快速识别（不落任务）与任务式识别两种入口
- PDF 优先抽取文本层，无文本层则转图逐页 OCR；图片直接 OCR
- 正则解析：发票代码 / 号码（20 位或 8 位）、开票日期（中英格式）、金额、税额、价税合计、购销方、项目名（`\*类别\*项目`）；关键词判定 10 类发票类目
- 去重：同任务或跨任务同发票号，或同任务「同金额 + 同日期 + 同文件名」兜底
- 分组统计（按类目小计、非重复总额）
- 下载支持单张 / 按类目 / 全部，PDF 合并或 ZIP 打包
- Admin 建任务 → 上传端点同步识别（处理中 → 已完成）

## 目录结构

```
invoice_recognition/
├── apps.py                          # AppConfig
├── models.py                        # 2 个 managed=False 镜像模型 + TextChoices
├── api/invoice_recognition_api.py   # 4 个端点
├── admin/invoice_recognition_admin.py
├── services/
│   ├── invoice_recognition_service.py  # 核心识别（任务/文件/OCR/解析/去重/统计）
│   ├── quick_recognition_service.py    # 快速识别（含异步批量版本）
│   ├── invoice_parser.py               # InvoiceParser 正则解析器 + ParsedInvoice
│   ├── invoice_download_service.py     # 下载（PDF 合并 / ZIP）
│   ├── recognition_result.py           # RecognitionResult dataclass
│   └── wiring.py                       # 依赖装配
└── templates/admin/invoice_recognition/  # 任务 change_form
```

## 数据模型

- `InvoiceRecognitionTask` — 发票识别任务（`managed=False`，`db_table="automation_invoicerecognitiontask"`）
- `InvoiceRecord` — 发票记录（`managed=False`，`db_table="automation_invoicerecognitionrecord"`）

> 两模型的**表结构归 automation app 管理**（历史迁移兼容），本 app 无 migrations，仅镜像映射以便服务层与 Admin 使用。

## API 端点

前缀 `/api/v1/invoice-recognition`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/quick-recognize` | 快速识别（不落任务） |
| POST | `/{task_id}/upload` | 上传并同步识别（限流 UPLOAD） |
| GET | `/{task_id}/status` | 任务状态与分组统计 |
| GET | `/{task_id}/download` | 下载（scope=single/category/all，fmt=pdf/zip，限流 EXPORT） |

## Admin

只注册 `InvoiceRecognitionTask`；允许新增（表单仅 name 字段），change_view 注入分组数据渲染自定义模板，列表显示「非重复总金额」。

## 异步任务与信号

无（识别在上传请求内同步完成，无定时任务/信号）。

## 外部集成

- OCR 经 `apps.core` ServiceLocator；PDF 文本抽取用 automation 的 `PDFTextExtractor`；PyMuPDF 合并 PDF
- 解析完全基于正则与关键词，无 LLM

## 依赖模块

- `apps.automation`（OCR / PDF 文本抽取）、`apps.core`（协议、异常、限流、认证）
