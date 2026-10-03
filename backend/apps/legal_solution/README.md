# 📋 法律服务方案（legal_solution）

输入案情简述，自动串联「类案检索 → 七段式 LLM 方案生成 → HTML 报告 → PDF 导出」的法律服务方案生成器。无自有 API，全部入口在 Django Admin。

## 功能概述

- Django-Q 异步任务五阶段：提取关键词 → 创建并轮询 legal_research 检索任务（2s 轮询 / 10 分钟超时）→ 分段生成 → 组装 HTML → 判定 COMPLETED / PARTIAL
- 七个固定段落：案情分析 / 法律关系 / 争议焦点 / 类案参考 / 诉讼策略 / 风险评估 / 费用预估；后段 prompt 依赖前段内容，单段失败不中断整体
- 段落级「调整」：用户提交 feedback 后 version+1 重新生成单段并重渲染 HTML、清 PDF 缓存
- 类案上下文来自关联 `research_task.results`（rank/标题/案号/法院/相似度/摘要 300 字截断）

## 目录结构

```
legal_solution/
├── apps.py / tasks.py / signals.py   # Q 任务入口 / post_delete 清 PDF
├── models/                           # task.py=SolutionTask、section.py=SolutionSection
├── admin/task_admin.py               # 唯一 Admin（无 api 包）
├── services/
│   ├── solution_generator.py         # 段落生成 + md→html（LLM chat temperature=0.4、重试 2 次、bleach 白名单消毒）
│   ├── task_service.py               # 创建/派发/重生成段落
│   ├── html_renderer.py              # 渲染 report.html 模板
│   ├── pdf_exporter.py               # WeasyPrint
│   └── prompts.py                    # build_section_prompt
└── templates/legal_solution/report.html
```

## 数据模型

- `SolutionTask` — 案情简述、关键词、站点凭证、关联检索任务、状态、进度、HTML、PDF、LLM 模型、q_task_id
- `SolutionSection` — 段落（段落类型唯一、order、markdown/HTML 内容、prompt_used、user_feedback、version、状态、metadata）

## 使用方式（Admin）

`SolutionTaskAdmin` + `SolutionSectionInline`：

1. 新建表单填 case_summary / 选择威科凭证（律所隔离过滤）/ 选择 LLM 模型（动态下拉），保存即派发队列
2. 自定义 URL：`preview/`（HTML 预览）、`pdf/`（PDF，带缓存复用）、`sections/<id>/adjust/`（GET 调整表单 / POST 重生成单段）、`regenerate-html/`

## 异步任务与信号

- Q 任务 `run_solution_task`；signal：post_delete 清理 `pdf_file`；无定时任务

## 设计要点

- 关键词提取复用 legal_research 的 `LegalResearchExecutor` 内部方法（跨 app 私有 API 依赖）
- 任务为同步轮询设计（time.sleep）；若改 async 需换 asyncio.sleep

## 外部集成

LLM（ServiceLocator.get_llm_service）、WeasyPrint、间接依赖威科先行（通过 legal_research 任务）

## 依赖模块

- `apps.core`、`apps.legal_research`、`apps.organization`
