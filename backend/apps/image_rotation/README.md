# 🔄 图片自动旋转（image_rotation）

批量图片 / PDF 页面的方向自动纠正工具（ONNX 分类或 OCR 四方向投票），附带 OCR 文本提取、LLM 智能重命名（日期 + 金额）、导出 ZIP/PDF 与历史任务管理。从 automation 拆分的独立 app。

## 功能概述

- PDF 快速拆页（PyMuPDF 150DPI，上限 50MB / 100 页）并逐页检测方向
- 两种方向检测：`onnx`（微调 ConvNeXtV2-Atto 分类，置信度 ≥ 0.65 才建议自动旋转）与 `ocr_voting`（0/90/180/270 四方向 OCR 得分投票）；批量并发（Semaphore(8)）
- OCR 文本提取（provider=local 或 paddleocr_api）
- LLM 自动重命名：从 OCR 文本提取日期（YYYYMMDD）+ 金额生成 `日期_金额.ext`；有原图时先走重命名专用高精度 OCR 通道（预处理增强 + 置信度过滤）
- 导出：ZIP（支持 rename_map 重命名）与 PDF（A4/A3/letter/original 纸张适配）
- 历史任务：创建 / 列表 / 详情 / 重跑 OCR / 批量改角度与文件名 / 保存导出 URL / 下载 / 改名 / 删除
- 端点级限流（UPLOAD / LLM / EXPORT 配置键）

## 目录结构

```
image_rotation/
├── apps.py / models.py / signals.py
├── api/image_rotation_api.py        # 全部端点
├── admin/                           # Tool 工作台 + 历史任务 Admin
├── services/
│   ├── facade.py                    # ImageRotationService：export_images / export_as_pdf
│   ├── pdf_extraction_service.py    # PDF→页图 + 方向
│   ├── orientation/                 # OCR 四方向投票 + ONNX 分类服务（HF Hub 自动下载）
│   ├── auto_rename_service.py       # LLM 提取 + 文件名生成
│   ├── rename_ocr/                  # 重命名专用高精度 OCR 通道（预处理/置信度过滤）
│   ├── transform/                   # EXIF 清理 / 旋转 / 纸张缩放 / PDF 导出旋转
│   ├── export/                      # PDF / ZIP 导出器
│   ├── job_service.py               # 历史任务 CRUD + 重跑 OCR
│   ├── storage.py / validation.py   # 输出目录与格式校验
├── static/image_rotation/           # 工具页 CSS/JS
└── templates/admin/image_rotation/  # 工具页 + partials
```

## 数据模型

- `ImageRotationTool` — managed=False 虚拟模型，Admin 入口
- `ImageRotationJob` — 历史任务（UUID 主键）
- `ImageRotationPage` — 单页记录（源图 FileField、检测角度、ONNX 角度、置信度、OCR 文本、建议文件名、source_type=image/pdf_page）

## API 端点

前缀 `/api/v1/image-rotation`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/extract-pdf-fast` | PDF 快速拆页 |
| POST | `/detect-page-orientation`、`/detect-orientation` | 方向检测 |
| POST | `/extract-text` | OCR 文本提取 |
| POST | `/suggest-rename` | LLM 重命名建议 |
| POST | `/export`、`/export-pdf` | 导出 ZIP / PDF |
| POST/GET | `/jobs`、GET/PATCH/DELETE `/jobs/{job_id}` | 历史任务 CRUD |
| POST | `/jobs/{job_id}/ocr` | 重跑 OCR |
| PATCH | `/jobs/{job_id}/pages` | 批量修改角度与文件名 |
| POST | `/jobs/{job_id}/save-export-url` | 保存导出 URL |
| GET | `/jobs/{job_id}/download/{file_type}` | 下载导出文件 |

## Admin

- `ImageRotationTool` changelist 渲染完整工具页（专属 CSS/JS 与 partials 模板）；`ImageRotationJob` 全只读 + Page Inline

## 异步任务与信号

- 无定时任务；signals：Page 删除清源图、Job 删除清 flat 导出文件并兜底 rmtree 任务目录

## 外部集成

- ONNX 方向分类模型（本地 `assets/ml_models/orientation/`，缺失时从 HuggingFace Hub 固定 revision 下载）
- OCR（ServiceLocator 默认 + `paddleocr_api` provider）、LLM（ServiceLocator.get_llm_service）

## 依赖模块

- `apps.core`（ServiceLocator、IOcrService 协议、限流、认证、异常）、`apps.automation.services.ocr`
