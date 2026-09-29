# 🎬 故事可视化（story_viz）

把判决书等法律文书通过 LLM 流水线生成可交互的 HTML 可视化动画（时间线 / 人物关系图 / 诉求 vs 判决），并支持基于结果的 LLM 问答。

## 功能概述

- 三种可视化类型：`timeline`（时间线）、`relationship`（D3 人物关系图）、`claim_judgment`（诉求与判决对比）
- 五阶段流水线：预处理（清行 + 12000 字截断 + hash）→ LLM 提取事实（当事人/事件/关系/裁判结果）→ LLM 编排动画脚本 → 本地渲染布局 payload → LLM 生成 SVG 视觉片段 → 组装自包含 HTML
- 每阶段落库进度（10/35/60/80/90/100），阶段间检查 `cancel_requested`
- LLM 调用失败重试一次（temperature 0 → 0.3），再失败走降级 fallback，不中断任务
- 相同 viz_type + 全文 SHA-256 去重复用已有任务
- 完成后可预览 HTML、基于 facts_payload 的 LLM 问答、失败/取消后重试
- 可选指定 LLM 模型（Admin 下拉与 `/animations/models` 来自 LLMConfig + ModelListService）

## 目录结构

```
story_viz/
├── apps.py / tasks.py
├── models/story_animation.py      # StoryAnimation + TextChoices
├── api/animation_api.py           # 全部端点
├── schemas/                       # ExtractedFacts / AnimationScript 结构化输出 Schema
├── services/
│   ├── job_service.py             # 创建/去重/状态/取消/重试/ask
│   ├── workflow_service.py        # 五阶段流水线编排
│   ├── preprocess_service.py      # 文书预处理
│   ├── fact_extraction_service.py # LLM 事实提取（structured_output）
│   ├── animation_script_service.py# LLM 动画脚本编排
│   ├── svg_layout_renderer_service.py      # 本地布局渲染
│   ├── svg_fragment_generator_service.py  # LLM 生成 SVG 片段
│   ├── html_composer_service.py   # 组装自包含 HTML（暗色玻璃风，内嵌 D3）
│   └── wiring.py
├── admin/story_animation_admin.py
└── templates/admin/story_viz/storyanimation/change_form.html
```

## 数据模型

- `StoryAnimation` — 可视化任务（UUID 主键；viz_type / status / current_stage / progress / cancel_requested / llm_model / source_hash / facts_payload / script_payload / render_payload / animation_html）

## API 端点

前缀 `/api/v1/story-viz`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/animations/{id}` | 任务状态 |
| POST | `/animations/{id}/retry`、`/cancel` | 重试 / 取消 |
| GET | `/animations/{id}/preview` | 预览 HTML（直接返回，未完成 409） |
| GET | `/animations/{id}/detail` | 详情 |
| POST | `/animations/{id}/ask` | 基于结果的问答（仅 completed） |
| GET | `/animations/models` | 可用 LLM 模型列表 |

## Admin

- 新建表单即触发异步任务（save_model → create_from_admin）；LLM 模型下拉、进度条、彩色状态列、批量重排队 action；change_view 注入 7 个 API 地址

## 异步任务与信号

- `tasks.generate_story_animation` / `agenerate_story_animation`：经 core 任务提交服务派发；无定时任务/信号

## 外部集成

- LLM（`apps.core.llm`：build_llm_service、structured_output、LLMConfig、ModelListService）；SVG 片段由 LLM 生成（system prompt 禁止 script 标签）

## 依赖模块

- `apps.core`（llm、任务提交依赖）
