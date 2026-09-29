# 🤖 AI 诉讼文书（litigation_ai）

两大子系统：① 诉讼文书生成会话（`/litigation`，对话式引导 + 证据 RAG + 草稿生成）；② 模拟庭审（`/mock-trial`，多智能体辩论 / 交叉询问 / 法官视角 / 报告导出）。

## 功能概述

- 诉讼文书生成会话：会话 CRUD、消息流、`/generate` 生成任务 + `/tasks/{task_id}` 轮询
- 模拟庭审：会话管理、报告（`/report`）、导出（`/export`）、多智能体对抗（adversarial / cross_exam / debate / judge_perspective）
- WebSocket 双通道：`ws/litigation/sessions/<id>/` 与 `ws/mock-trial/sessions/<id>/`（Channels，实时交互）
- 证据 RAG 链：digest → text extraction → embedding → vector store → rag（pgvector）
- 链式任务编排（chains 5 条）：goal_intake、document_type_parse、litigation_draft、user_choice_parse、mock_trial_chains
- Agent 体系：factory / tools / prompts / middleware / llm_provider

## 目录结构

```
litigation_ai/
├── api/            # litigation_api（8 端点）+ mock_trial_api（6 端点）
├── consumers/      # LitigationConsumer + MockTrialConsumer（WebSocket）
├── routing.py      # WS 路由
├── services/
│   ├── session/    # 会话生命周期 / 消息 / 上下文 / conversation_flow 等 7 个
│   ├── generation/ # document_generator / draft / litigation_agent / placeholder_render / prompt_template
│   ├── evidence/   # 5 个 RAG 组件
│   └── mock_trial/ # adversarial / agents / cross_exam / debate / judge_perspective /
│                   #   mock_trial_flow / report / export / types 共 9 个
├── chains/ + agent/ + placeholders/（含 mock_trial_report）
└── models/         # LitigationSession（session_type：DOC_GEN / 模拟庭审 MockTrialMode）、EvidenceChunk
```

## API 端点

前缀 `/api/v1/litigation` 与 `/api/v1/mock-trial`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | `/sessions`、GET/PATCH/DELETE `/sessions/{id}` | 诉讼会话管理 |
| GET | `/sessions/{id}/messages`、POST `.../generate`、GET `/tasks/{task_id}` | 消息与生成 |
| POST/GET | `/sessions`、GET `/sessions/{id}` | 模拟庭审会话 |
| GET | `/sessions/{id}/report`、`/export`、DELETE `/sessions/{id}` | 庭审报告与导出 |

## 数据模型

- `LitigationSession` — 会话（session_type 区分文书生成 / 模拟庭审，MockTrialMode 枚举）
- `EvidenceChunk` — 证据分块（embedding / vector store 用）

## 外部集成

LLM（agent/llm_provider）、pgvector、Channels（WebSocket）；无 admin、无定时任务。

## 依赖模块

- `apps.core`（LLM、ServiceLocator、异常）、`apps.cases`（证据 digest）、`apps.documents`（占位符与模板）
