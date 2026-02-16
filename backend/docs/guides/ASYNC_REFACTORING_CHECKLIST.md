# 异步化改造清单

## 分流原则（建议默认阈值）

| 类型 | 适用场景 | 建议阈值 | 交互形态 |
|---|---|---|---|
| 同步 | 纯 DB/轻量计算、稳定快速 | P95 < 2s | 直接返回结果 |
| 异步视图（async） | I/O 密集（外部 HTTP/模型调用），但希望“即时响应/可流式” | 2–30s | SSE/WS 流式输出或一次性返回 |
| 后台任务（django-q） | 不确定耗时、可能分钟级、CPU/OCR/Playwright | P95 > 5s 或不稳定 | submit + task_id + status/result（可 WS 推送） |

## 当前项目的优先改造点（按收益排序）

### 1) LLM 对话：改 async + 流式（提升用户体验最大）
- 入口：[ninja_llm_api.py:chat_with_context](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/core/api/ninja_llm_api.py#L62-L87)
- 问题：同步 handler 容易占用线程；无法做到逐步输出。
- 建议：改 `async def` 并提供 SSE/WS 流式输出；把长文本分析类请求（可分钟级）分流到后台任务。

### 2) 证件识别：改后台任务（避免 120s 阻塞/超时）
- 入口：[clientidentitydoc_api.py:recognize_identity_doc](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/client/api/clientidentitydoc_api.py#L188-L258)
- 耗时来源：OCR + Ollama（当前 Ollama 客户端同步且超时 120s）：[ollama_client.py](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/services/ai/ollama_client.py#L8-L65)
- 建议：submit → task_id；提供 status/result；前端可轮询或 WS 推送。

### 3) 文书送达手动查询：改后台任务（Playwright/外站交互分钟级）
- 入口：[document_delivery_api.py:manual_query](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/document_delivery_api.py#L180-L206)
- 问题：同步执行 `query_and_download(...)`，极易触发网关/worker 超时。
- 建议：手动接口改为入队执行；保留原定时能力，统一任务模型与状态查询。

### 4) 文档处理/自动命名：按阈值分流（小任务同步，大任务后台）
- 入口示例：
  - [document_processor_api.py](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/document_processor_api.py)
  - [auto_namer_api.py](file:///Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/automation/api/auto_namer_api.py)
- 耗时来源：PDF 渲染/OCR/磁盘 I/O/LLM。
- 建议：强制页数/大小上限；超过阈值返回“已转后台处理 + task_id”。

## 采样与画像建议
- 开启请求耗时 header 与日志：设置环境变量 `DJANGO_REQUEST_TIMING=true`（可选 `DJANGO_REQUEST_TIMING_LOG=true`）。
- 以 P95/P99 决策：优先处理 P95>2s 的 I/O 链路与 P95>5s 的长任务链路。

