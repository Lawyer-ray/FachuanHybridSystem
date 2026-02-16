# 🤖 AI 诉讼文书模块 (Litigation AI)

Litigation AI 模块负责面向“诉讼文书生成/对话式引导”的 AI 能力：会话与状态管理、链式任务编排（chains）、Agent 工具与提示词（prompts），并提供 API 与 WebSocket（Channels）交互入口。

## 📚 模块概述

本模块提供：
- 会话/证据相关模型与存储（session、evidence_chunk 等）
- 对话流程编排与状态机（flow）
- LLM/Agent 抽象与工具调用（agent）
- 诉讼目标采集、文书类型解析、草稿生成等链路（chains）
- API + WebSocket consumer，支持前端实时交互式生成

## 📁 目录结构（简要）

```
litigation_ai/
├── api/        # Ninja API
├── consumers/  # Channels consumer（WebSocket）
├── services/   # 会话、对话、生成、RAG、向量存储等服务
├── chains/     # 目标采集/解析/草稿生成等链式编排
├── agent/      # Agent 工厂、工具、提示词与中间件
├── models/     # session / evidence_chunk 等
└── placeholders/ # 诉讼上下文占位符与规范
```

## 🔑 核心入口

- API：`api/litigation_api.py`
- WebSocket：`consumers/litigation_consumer.py`、`routing.py`
- 流程编排：`services/flow/flow_state_machine.py`、`services/conversation_flow_service.py`
- 生成与证据：`services/document_generator_service.py`、`services/evidence_rag_service.py`

