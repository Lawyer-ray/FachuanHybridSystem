# ✂️ PDF 拆解（pdf_splitting）

把一份大的诉讼/立案材料 PDF 按内容识别（OCR + 关键词模板）、按页或手动三种模式拆分成多个命名 PDF 片段，人工复核确认后打包 ZIP 导出。

## 功能概述

- 三种拆分模式：`content_analysis`（内容识别）、`page_split`（每页一片、分析后自动导出）、`manual_split`（跳过后台分析直接进入待复核）
- OCR 三档（fast / balanced / accurate，不同 DPI、模型与并发），本地并行 OCR + 按 PDF SHA-256 的页面级缓存
- 云端解析优先：经 `ParserFactory` 选择 mineru / textin 后端整本解析，失败自动降级本地 OCR，降级原因写入 summary
- 基于片段模板（`filing_materials_v1` 立案材料，15 种片段类型）做强/弱/负向/续页关键词评分 + Levenshtein 模糊匹配 + 版面标题辅助命名
- 起诉状结尾探测（终止词 + 附件信号）、跨页续页上下文推理、相邻主体信息段合并、未识别区间 gap 自动补片
- 复核确认端点会重排片段、查重叠、自动补 gap，然后异步导出 ZIP
- 支持上传文件或服务器本地绝对路径两种来源（拒绝 `smb://`）；上限 150MB / 300 页

## 目录结构

```
pdf_splitting/
├── apps.py                       # AppConfig，ready() 导入 signals
├── models.py                     # 3 个模型 + 6 组 TextChoices
├── api/pdf_splitting_api.py      # Ninja 路由
├── admin/pdf_splitting_admin.py  # Tool 工作台 + Job Admin
├── services/
│   ├── job_service.py            # 任务创建/校验/确认/取消/状态
│   ├── template_registry.py      # 片段模板定义（filing_materials_v1）
│   ├── storage.py                # PdfSplitStorage（jobs/{id}/...）
│   └── split/
│       ├── service.py            # PdfSplitService facade：analyze/export/render
│       ├── ocr_handler.py        # 档位解析、并行 OCR、云后端选择、SHA-256 页缓存
│       ├── segment_detector.py   # 评分/检测/推理/合并/gap 填充
│       ├── export_utils.py       # 片段 PDF 导出 + 文件名去重
│       └── split_models.py       # PageDescriptor/SegmentDraft/OCRRuntimeProfile
├── tasks.py                      # execute_pdf_split_job / export_pdf_split_job
├── signals.py                    # post_delete 清理任务目录
└── templates/admin/pdf_splitting/  # workbench / change_form / pdf_preview（PDF.js 预览页）
```

## 数据模型

- `PdfSplittingTool` — managed=False 虚拟模型，Admin 工作台入口
- `PdfSplitJob` — 拆解任务（UUID 主键、模板键/版本、OCR 档位、拆分模式、进度、导出 ZIP 路径）
- `PdfSplitSegment` — 拆解片段（页区间、类型、置信度、来源方法、复核标记）

## API 端点

前缀 `/api/v1/pdf-splitting`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/jobs` | 创建任务（`file` 或 `source_path` 二选一 + template_key / split_mode / ocr_profile） |
| GET | `/jobs/{job_id}` | 任务状态与片段列表 |
| GET | `/jobs/{job_id}/pages/{page_no}/preview` | 页面 PNG 预览 |
| POST | `/jobs/{job_id}/confirm` | 复核确认并触发导出 |
| POST | `/jobs/{job_id}/cancel` | 取消 |
| GET | `/jobs/{job_id}/download` | 下载导出 ZIP |
| GET | `/jobs/{job_id}/pdf`、`/preview-page` | 原始 PDF（供 PDF.js）/ HTML 预览页 |

## Admin

- `PdfSplittingTool` changelist 渲染工作台；`PdfSplitJob` 全只读，change_view 注入 API 地址给自定义模板

## 异步任务与信号

- `execute_pdf_split_job`：分析与片段识别主流程；`export_pdf_split_job`：确认后导出 ZIP
- `signals.post_delete(PdfSplitJob)`：清理任务目录
- 取消检查与进度每 5 页更新一次

## 外部集成

- 云端解析：`apps.document_parsing`（mineru / textin，经 ParserFactory）
- 本地 OCR：`apps.automation.services.ocr.ocr_service.OCRService`
- PyMuPDF（页面渲染与片段切割）

## 依赖模块

- `apps.core`：任务提交、异常、storage_service
- `apps.automation`（OCR）、`apps.document_parsing`（云解析）
