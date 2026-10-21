# Agent 运行时（`apps/agent`）

把 agent 循环建在 **pi**（`@earendil-works/pi-coding-agent`）上，独立于
`apps.workbench`，为高并发与多入口（对话 / 案件内 / 任务式）打底。

---

## 1. 为什么独立成 app

`apps/workbench` 的 `chat_service.py`（566 行）把 Pydantic AI 逻辑与 SSE 编排焊死
在一起，且其 `WorkbenchSession` / `ApprovalManager` 带有该域的批量分析语义与
纯内存审批。

在本 app 里重建，换来三件事：

| | workbench | **agent** |
|:-|:-|:-|
| 审批状态 | 纯内存，进程重启即丢 | **落库，可审计、可超时** |
| 会话状态 | 与批量分析等语义混杂 | **纯净会话/消息两表** |
| 并发 | 单队列串行 | **进程池 + 共享 MCP** |

`workbench` 保持原样不动，作为既有功能的回退路径。

## 2. 为什么是 pi

三个候选 runtime 里，只有 pi 同时满足三条硬约束：

| 约束 | pi 的满足方式 |
|:-|:-|
| 工具调用前能阻塞等人工审批 | `tool_call` 钩子返回 `{ block: true }` |
| 能挂起等外部系统决策 | 钩子内 `await fetch(...)`（实测 allow/reject/timeout 三路） |
| 能吃下 378 个 MCP 工具 | 实测 `fachuan: connected, 378 tools` |

对照：DSH 的 Python SDK 实测收不到审批事件；goose 的 ACP 协议支持但本地网关不兼容。

## 3. 高并发：共享 MCP 是关键

### 实测数据

| 模式 | 8 并发总耗时 | MCP 内存 |
|:-|:-|:-|
| 每进程各起 stdio MCP | 4.1s | 8 × 225MB ≈ **1.8 GB** |
| **一份常驻 + HTTP 共享** | **3.4s** | **71 MB** |

单个 `python -m mcp_server`：**225MB / 冷启动 6 秒**。
若每个 pi 各起一份，20 并发就是 4.5GB，且每路首响应都等 6 秒。

### 做法

```
Django / 部署脚本
  └─ 一份 MCP 常驻于 http://127.0.0.1:8011/mcp   (streamable-http)

pi 进程池（N 个）
  └─ .pi/mcp.json 指向上面那个 endpoint
```

`mcp_server/__main__.py` 增加 `FACHUAN_MCP_TRANSPORT` 开关，**默认 stdio 保持
既有行为完全不变**；设为 `streamable-http` 才启用共享模式。

### 进程池

pi 的 session 是进程内状态，单进程切 session 会串行。因此用进程池：

- `FACHUAN_AGENT_POOL_SIZE` 控制容量（默认 4，上限 32）
- 归还时检查进程存活，崩溃的进程不会回池
- 每个会话有独立临时工作目录（内含一份 `.pi/mcp.json`）

## 4. 审批链路

```
pi 决定调用 mcp__fachuan__delete_case
  │
  ├─ approval-gate.ts 命中 HIGH_RISK_TOOLS
  │     └─ POST /api/v1/agent/approval/request   （同步阻塞）
  │           ├─ 建 AgentApproval(pending)
  │           ├─ 经 event_bus 推 SSE approval_request 给前端
  │           ├─ 等 POST /api/v1/agent/approval/{id}/decide
  │           └─ 返回 {"approved": bool}
  │
  ├─ true  → 工具执行
  └─ false → { block: true }，模型收到拒绝理由
```

**两层防护**：extension 侧清单命中即回调；服务端 `HIGH_RISK_TOOLS` 二次判定，
即便 extension 被绕过也拦得住。两份清单一致性由单测守护
（`test_server_and_extension_lists_in_sync`）。

**fail-closed**：只有 `status=approved` 放行。无 SSE 通道 / 网络失败 / 用户超时，
一律拒绝。

**为什么审批需要 event_bus**：审批走独立 HTTP 回调，它与「发起对话的 SSE 连接」
不在同一调用栈，必须按会话寻址才能把 `approval_request` 推给正确的前端。

## 5. 端点

前缀 `/api/v1/agent`：

| 方法 | 路径 | 说明 |
|:-|:-|:-|
| POST | `/sessions` | 新建会话 |
| GET | `/sessions` | 列出会话 |
| DELETE | `/sessions/{id}` | 删除会话 |
| POST | `/sessions/{id}/messages` | 发消息（SSE 流） |
| POST | `/approval/request` | **pi extension 回调**（`X-Internal-Token` 鉴权） |
| POST | `/approval/{id}/decide` | 前端提交审批决定 |
| GET | `/approvals` | 审批记录（审计） |

## 6. 事件契约

```
meta → activity → delta* → tool_call*/tool_result* → approval_request? → error? → done
```

与 `workbench` 的事件契约一致，前端可复用现有渲染逻辑。

## 7. 配置

| 环境变量 | 默认 | 说明 |
|:-|:-|:-|
| `FACHUAN_PI_BIN` | `which pi` | pi 可执行文件 |
| `FACHUAN_PI_MODEL` / `FACHUAN_PI_PROVIDER` | — | 透传 `pi --model/--provider` |
| `FACHUAN_PI_APPROVAL_EXTENSION` | 内置路径 | 审批 extension |
| `FACHUAN_APPROVAL_URL` | `127.0.0.1:8002/api/v1/agent/approval/request` | 审批端点 |
| `FACHUAN_INTERNAL_TOKEN` | 空 | 服务间鉴权（**生产必须配置**） |
| `FACHUAN_AGENT_POOL_SIZE` | 4 | 进程池容量 |
| `FACHUAN_MCP_SHARED` | 1 | 共享 MCP 开关 |
| `FACHUAN_MCP_HTTP_PORT` | 8011 | 共享 MCP 端口 |

## 8. 部署前置

后端机器需要 **Node.js >= 22.19.0 + pi**：

```bash
npm install -g @earendil-works/pi-coding-agent
pi --version   # 1.3.0
```

这是引入 pi 的唯一部署成本（`tool_call` 钩子只能用 TypeScript 写）。

共享 MCP 需要在应用启动前拉起（或由首次调用懒启动）：

```bash
FACHUAN_MCP_TRANSPORT=streamable-http FACHUAN_MCP_HTTP_PORT=8011 \
  python -m mcp_server
```

## 9. 目录结构

```
apps/agent/
├── apps.py
├── models/agent.py          # AgentSession / AgentMessage / AgentApproval
├── api/agent_api.py         # 会话、对话、审批端点
├── services/
│   ├── chat_service.py      # 对话编排
│   ├── approval.py          # 审批策略 + 阻塞等待
│   └── event_bus.py         # 按会话分发事件
├── pi/
│   ├── rpc_client.py        # RPC 协议（二进制按 LF 切分）
│   ├── pool.py              # 进程池
│   ├── bridge.py            # pi 事件 → 前端事件
│   ├── shared_mcp.py        # 共享 MCP 管理
│   └── approval-gate.ts     # pi 侧审批 extension
└── migrations/
```

## 10. 验证状态

| 项 | 状态 |
|:-|:-|
| 单元测试（翻译 / 审批 / 总线 / 共享 MCP） | ✅ 18 passed |
| ruff check / format | ✅ |
| Django `manage.py check` | ✅ 0 issues |
| RPC 真实对话 | ✅ 输出「接入成功」 |
| MCP 378 工具（共享 HTTP） | ✅ `fachuan: connected, 378 tools` |
| 8 并发（共享 MCP） | ✅ 3.4s / 71MB |
| Django HTTP 端点联调 | ⏳ 待起服务验证 |
| 共享 MCP 跨 worker 广播 | ⏳ 当前为进程内总线，多 worker 需换 Redis |
