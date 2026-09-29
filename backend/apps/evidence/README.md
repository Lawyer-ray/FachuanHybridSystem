# 📁 证据管理（evidence）

案件证据清单管理：证据清单 / 明细维护、证据文件上传（SHA-256 去重 + OCR 全文）、异步 PDF 合并（连续页码）、Word 导出、AI 证明目的 / 质证意见辅助与「开庭模式」视图。

> **历史兼容设计**：`EvidenceList` / `EvidenceItem` 的 `Meta.app_label="documents"`、`db_table="documents_evidencelist"`——模型物理上属 documents app，本 app 通过 proxy 模型接管 Admin 与服务层（apps.ready() 会注销 documents 下的原始模型 admin，证据 admin 统一在 `/admin/evidence/`）。

## 功能概述

- 每案件最多 6 份证据清单（list_1 ~ list_6），按 `previous_list` 链式关联，自动计算跨清单连续序号（start_order）与连续页码（start_page，含循环引用检测）
- 证据文件上传（PDF/Office/图片，上限 50MB），自动计算 SHA-256、PDF 页数，异步触发 OCR 提取全文（供搜索）
- 异步 PDF 合并：Admin action 提交 Django-Q 任务，模型上完整合并状态机（pending/processing/completed/failed + 进度），合并后自动重算页码并更新后续清单
- Word 导出：默认表格导出与 docxtpl 模板导出（复用 documents.DocumentTemplate，限证据材料类模板），版本号自动递增；支持 ZIP 打包
- AI 辅助：LLM 生成「证明目的建议」与「质证意见」（真实性/合法性/关联性三性 JSON）
- Admin「开庭模式」：按案件汇总全部证据（全局序号、三性、质证意见、OCR 文本）的只读庭审视图

## 目录结构

```
evidence/
├── apps.py                     # ready()：注销 documents 原 admin + 挂 signals
├── models/                     # enums / evidence / evidence_storage / group / proxy
├── api/evidence_api.py         # reorder + 2 个 AI 端点
├── schemas.py
├── services/
│   ├── wiring.py               # 依赖装配
│   ├── core/                   # EvidenceService 门面 + query/mutation/file/page_range + 访问策略
│   ├── mutation/               # 合并用例（select_for_update 抢锁 + 节流进度上报）
│   ├── infrastructure/         # PDF 合并工作流 + pdf_utils 薄包装
│   ├── export/                 # Word 导出 + 占位符上下文
│   ├── admin/                  # Admin 层门面
│   └── ai/                     # 证明目的/质证意见 + OCR/全文搜索
├── admin/                      # 清单/明细/分组 Admin + 开庭模式 + 表单/Inline/Mixin
├── tasks.py                    # merge_evidence_pdf_task / ocr_evidence_item_task
└── signals.py                  # post_delete 清理物理文件
```

## 数据模型

- `EvidenceList` — 证据清单（链式前置关联、清单类型、合并状态机）
- `EvidenceItem` — 证据明细（名称、页数、三性、质证意见、OCR 文本、文件哈希）
- `EvidenceGroup` — 争议焦点分组
- `EvidenceListProxy` / `EvidenceItemProxy` — 代理模型（admin 归位到 /admin/evidence/）

## API 端点

前缀 `/api/v1/evidence`（其余操作经 Django Admin 自定义视图完成）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/evidence-lists/{list_id}/reorder` | 重排证据明细（带案件访问校验） |
| POST | `/ai/suggest-purpose` | AI 证明目的建议 |
| POST | `/ai/generate-cross-examination` | AI 质证意见生成 |

## 核心服务

- `EvidenceService`（门面）+ core 层四件套：Query / Mutation / File / PageRangeCalculator
- 合并：`EvidenceMergeUseCase` + 继承 core `PDFMergeServiceBase` 的合并工作流（乐观幂等：COMPLETED 且已有 PDF 直接返回）
- 导出：`EvidenceExportService` + `EvidenceListPlaceholderService`（占位符上下文）
- AI：`EvidenceAIService`、`EvidenceOCRService`、`EvidenceSearchService`

## Admin

- `EvidenceListProxy`：合并 / 导出 Word / 导出 ZIP 批量 action、7 个自定义 URL（next-list-type、merge、merge-status、export、download、reorder、recount-pages）、开庭模式入口、拖拽排序脚本；changelist 批量预计算 start_order/start_page 消 N+1
- `EvidenceItemProxy`：三性 / 质证 / OCR 字段组；`EvidenceGroupAdmin`

## 异步任务与信号

- `merge_evidence_pdf_task` / `ocr_evidence_item_task`（core.tasking 提交）
- signals：post_delete 清理证据文件与合并 PDF（on_commit）

## 外部集成

- LLM（apps.core.llm）、OCR（ServiceLocator）、PyMuPDF、docxtpl/python-docx、documents 的 pdf_merge_utils

## 依赖模块

- `apps.cases`（Case、CaseAccessPolicy）、`apps.documents`（模板、合并工具、占位符 fallback）、`apps.core`、`apps.organization`
