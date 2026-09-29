# 🧠 工作台（workbench）

AI 对话式操作中心：基于 Pydantic AI 多 Agent + MCP 工具集的 SSE 流式对话，附带法律文档批量分析任务。

## 功能概述

- 会话 CRUD + 消息持久化（user/assistant/tool 三角色，含 tool_input/tool_output）
- SSE 流式对话（meta / activity / delta / tool_call / tool_result / handoff / approval_request / done 事件）
- **多 Agent**：triage 分诊 + case / contract / research 三个专业 Agent（handoff 工具互转，共享一个 MCPToolset，按工具名关键字过滤各 Agent 可见工具）
- **Human-in-the-Loop 审批**：MCP `process_tool_call` 拦截 6 个高风险工具（delete_case / delete_client / delete_contract / send_document / file_lawsuit / submit_court_document），推送 SSE 审批事件并阻塞等待 `/workbench/approval` 响应（300s 超时，校验同一用户）
- 对话记忆：滑动窗口加载历史（10k token / 100 条）+ 超过 30 条自动生成摘要存 session.metadata；UsageLimits（50 请求 / 100k token）
- **批量文档分析**：Word（每文件一项）+ Excel（每行一项拆成 txt），Django-Q 异步并发 LLM 分析，SSE 进度流、取消、失败重试、CSV 汇总与 Markdown ZIP 下载
- **LLM 多 Key 轮询**：MultiKeyOpenAIModel 包装多个单 Key 模型，复用 core 的 KeyPool，全局并发上限 = Key 数 × 每 Key 上限
- 辅助 API：Prompt 优化（LLM 改写批量分析需求）、可用模型列表

## 目录结构

```
workbench/
├── apps.py
├── models/                    # session / message / batch_job（含 post_delete 清理信号）
├── api/workbench_api.py       # 全部端点
├── agents/
│   ├── definitions.py         # 4 个 Agent + build_model + 共享 MCPToolset（mcp_server 子进程）
│   ├── approval.py            # ApprovalManager + 高风险工具拦截
│   ├── deps.py / multi_key_model.py / http_client.py
├── services/
│   ├── chat_service.py        # 对话编排（队列桥接、历史、摘要、token 计量）
│   ├── session_service.py / message_service.py   # CRUD（权限过滤、缓存、游标分页、截断）
│   ├── batch_service.py       # 批量任务生命周期 + Excel 拆行
│   ├── doc_extractor.py       # docx/doc(LibreOffice)/txt 文本提取
│   └── dashboard_service.py   # 仪表盘聚合统计（供 core dashboard API 复用）
├── tasks/
│   ├── batch_runner.py        # Q2 入口（取消监视器、F() 原子计数、重试）
│   ├── registry.py / constants.py / parsing.py / summary.py
├── admin/ + schemas/
```

## 数据模型

- `WorkbenchSession` — 会话（UUID session_id、llm_model、storage_bytes）
- `WorkbenchMessage` — 消息（role/content/tool 四件套/metadata）
- `BatchJob` — 批量任务（job_type=doc_analysis、进度、cancel_requested、summary/detail_zip）
- `BatchJobItem` — 明细（file、result、duration_ms）

## API 端点

前缀 `/api/v1/workbench`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | `/sessions`、GET/PATCH/DELETE `/sessions/{id}` | 会话 CRUD |
| GET | `/sessions/{id}/messages`、DELETE `.../from/{message_id}` | 历史 / 截断重发 |
| PATCH | `/messages/{id}/feedback` | 消息反馈 |
| POST | `/sessions/{id}/messages/stream` | SSE 对话 |
| POST | `/approval` | 审批响应 |
| POST | `/batch/analyze`、GET `/batch/{id}/progress`、`/stream` | 批量分析与进度 |
| POST | `/batch/{id}/cancel`、`/retry` | 取消 / 重试 |
| GET | `/batch/{id}/download`、`/download-detail` | CSV 汇总 / Markdown ZIP |
| POST/GET | `/batch/{id}/messages`、`/sessions/{id}/batch-jobs` | 结果落为会话消息 / 关联任务 |
| POST/GET | `/optimize-prompt`、`/models` | Prompt 优化 / 模型列表 |

## 异步任务与信号

- tasks 包为 Django-Q2 批量分析入口（2 小时超时，线程池并发 LLM + 指数退避重试）
- 信号仅 BatchJob/Item 的 post_delete 文件清理；无定时任务

## 设计要点

- 共享单例 MCPToolset（进程内只起一个 mcp_server 子进程），Agent 间用 `mcp_server.filtered(fn)` 做工具可见性过滤
- 审批回调经 ContextVar（事件队列/agent 名/用户 ID）做到 per-request 隔离，多用户并发 SSE 互不串扰
- MultiKeyOpenAIModel 区分「建立失败换 Key 重试」与「流中途失败不换 Key」，避免重复输出；与 core 服务路径共用 KeyPool 防并发上限双份记账
- `LoopScopedTransport` 解决「进程级单例客户端 vs 事件循环绑定连接池」的矛盾
- 批量分析沿用 Job + Item 双层、协作式取消（DB cancel_requested 每 2s 轮询 + TaskRegistry）、节流式进度更新（每 5 项）

## 外部集成

MCP stdio server（backend/mcp_server）、OpenAI 兼容 LLM 平台（LLMConfig/KeyPool）、Django-Q2、LibreOffice（经 doc_converter 引擎转 .doc）

## 依赖模块

- `apps.core`（认证、权限、ServiceLocator、llm、upload_paths）、`apps.organization`；cases/contracts/reminders/client（仅仪表盘统计）、`apps.doc_converter`
