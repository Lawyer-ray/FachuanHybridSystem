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

`workbench`（旧 Pydantic AI 运行时）已于 v27.7.20 整体移除，本 app 是唯一的
AI 对话运行时；其中唯一被外部依赖的 `DashboardService` 已迁至 `apps/core/services/`。

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

### 进程闸门（每请求一个 pi 进程）

两个硬约束决定了进程**不复用**：

1. 审批 extension 在进程启动时读 `FACHUAN_SESSION_ID`/`FACHUAN_USER_ID` 环境变量，
   同一进程无法服务第二个会话（审批会推给错误的前端）；
2. pi 的会话是进程内状态，复用会把上一个用户的对话残留给下一个用户。

因此 `pool.acquire()` 每次解析稳定目录 → 渲染配置 → 起新进程 → 用完关闭；「池」
的作用退化为**限制并发数**（`FACHUAN_AGENT_POOL_SIZE`，默认 4，上限 32）。

**目录为什么不再随请求删除**：`--session-id` 按 cwd 隔离会话（见 §3.1），cwd
必须稳定，否则同一会话会变成两段互不相干的历史。含真实 API key 的
`models.json` 由 `write_models_json` 以 **0600 原子创建**、根目录 0700，
安全性不再依赖「用完就删」。

**排队可见 + 排队超时**：池满时不再无限等。第 5 个请求会先收到
`activity{status:"queued", position:N}`（前端显示「前方 N 人」），排队超过
`FACHUAN_AGENT_QUEUE_TIMEOUT`（默认 60s）抛 `PoolQueueTimeoutError`，前端收到
「当前使用人数较多，请稍后重试」而不是盯着转圈等到连接超时。

### 工具面：只声明 MCP 工具

pi 启动带 `--tools "mcp__fachuan__*"`，**内置的 read/bash/edit/write 全部不向模型
声明**——它们能以 Django 进程权限读写文件、执行命令，且不在审批清单内，是提示
注入直通服务器 RCE 的通道。审批 extension 缺失时进程拒绝启动（fail-closed）。

### 按用户身份执行（confused deputy 修复）

共享 MCP 是一份进程服务所有律师，而 `mcp_server` 默认用**服务账号（超管）**调
REST API——不区分身份的话，任何律师都能借 agent 读到全所数据、写操作审计也
记在服务账号名下。修复链路（378 个工具零改动）：

```
chat_service（每轮）
  └─ pi/user_token.py 为「当前律师」铸 access token（失败即整轮拒绝）
       └─ 注入 pi 进程 env：FACHUAN_USER_TOKEN
            └─ mcp.json: "Authorization": "Bearer ${FACHUAN_USER_TOKEN}"（pi 展开 env）
                 └─ mcp_server/identity.py 的 ASGI 中间件读头 → ContextVar
                      └─ client.py 优先透传 → REST API 以该律师身份执行
```

- 律师本人的归属过滤、权限、审计与直接登录完全一致；
- token 是无状态 access（寿命同全局配置，每轮重铸），只活在 pi 子进程 env 与
  临时目录 mcp.json 的**变量引用**里，不落盘明文；
- stdio 模式 / 无 Authorization 头 / 铸造失败：回退服务账号或拒绝执行，绝不
  静默提权。ContextVar 经 anyio `to_thread` 拷进工作线程，同步工具同样读得到。

### 多轮对话与系统提示词

**上下文归 pi 管**（`--session-dir` + `--session-id`）：每会话一个 session 文件，
pi 自己裁剪上下文并做自动 compaction（`docs/compaction.md`）。

相对旧方案（`--no-session` + 每轮渲染 transcript）的收益：

| | 旧（transcript） | **新（pi 原生 session）** |
|:-|:-|:-|
| 消息边界 | 压成纯文本，丢失 tool-call 协议 | pi 原生保留 |
| 前缀稳定性 | 每轮都变，prompt cache 打不中 | 增量追加，cache 可命中 |
| 长会话 | 30 条 / 24000 字符硬截断 | 自动 compaction |
| 工具调用史 | 变成「工具[x]: {...}」文本 | 原生结构化 |

`AgentMessage` 表仍然保留，作为**审计与回放**的权威：本轮助手文本与工具结果
在流结束时回写（取消/出错路径同样落库已流出的部分回答，`metadata.truncated=true`）。

**transcript 回退只在一种情况触发**：会话已有历史消息但没有 pi session 文件
（旧数据 / 目录被清理 / 换了部署节点）。此时用 `services/history.py` 渲染一次
补齐上下文，跑完这轮 pi 就有了自己的文件，下一轮自动回到正常路径。

系统提示词是工作目录里的 `AGENTS.md`（pi 无条件读取，与项目信任无关），模板在
本 app 内置，可用 `FACHUAN_PI_AGENTS_PATH` 覆盖。会话标题缺省取首条用户消息前
30 字；`SessionOut.llm_model` 回报的是服务端解析出的实际模型（客户端不传模型）。

### 3.1 pi session 存储（`pi/session_store.py`）

目录布局（根目录 `FACHUAN_AGENT_HOME`，默认 `~/.fachuan-agent`，权限 0700）：

```
<root>/
├── work/       # pi 的 cwd —— 必须稳定，--session-id 按 cwd 隔离会话
├── config/     # PI_CODING_AGENT_DIR：models.json / mcp.json / AGENTS.md / settings.json
└── sessions/
    └── <django-session-uuid>/
        └── <时间戳>_<同一 uuid>.jsonl
```

三个实测约束（都真踩过，别凭直觉改）：

1. **`--session-id` 按 project（cwd）隔离**：同一 id 换 cwd 会得到两个文件、
   模型完全失忆 → cwd 必须稳定；
2. **`PI_CODING_AGENT_DIR` 一改，sessions 也跟着走**：把配置目录与 session 目录
   分开设是没用的，pi 会忽略 `--session-dir` → 两者都在同一根目录下；
3. **没有可用模型时 pi 直接退出、不写文件**：所以「文件不存在」不是错误，
   只表示这轮没跑起来。

**删除会话会级联清理**：`delete_session()` 先按归属校验（越权者什么都删不掉），
再删数据库并 rmtree 对应 session 目录——那里含工具调用参数与工具返回的业务数据，
只删数据库会让用户误以为「会话已删干净」。孤儿目录用
`services/session_cleanup.purge_orphan_pi_sessions()` 定期清理。

**多 worker 部署要求**：session 目录必须被所有 worker 共享（NFS / 挂载卷），
否则同一会话落到不同 worker 时会看到两段互不相干的历史。单机多 worker 天然满足。

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

**两层防护**：extension 侧 `classifyRisk` 命中即回调；服务端 `classify_risk`
二次判定，即便 extension 被绕过也拦得住（客户端永远无权决定自己要不要审批）。

### 风险分级（不再是布尔）

`delete_case(case_id=1)` 与 `clear_all_xxx()` 走同一档审批时，用户无法区分
「删一条草稿」和「清空全库」，久了就闭眼点同意——审批形同虚设。现分四级：

| 级别 | 判定 | 交互 |
|:-|:-|:-|
| **低** | 读类（`list_`/`get_`/`search_`） | 直接执行 |
| **中** | 其他写类（`create_`/`update_`/`set_`） | 静默执行 + 日志审计标记 |
| **高** | `DANGER_PATTERNS`（删除/外发/递交/上传/归档确认）**或**写类参数含敏感字段 | 人工确认 |
| **紧急** | `CRITICAL_PATTERNS`（`clear_all`/`reset_and_`/`delete_all`/`bulk_delete`） | 二次确认 + 900s 超时 |

**参数级判定补的洞**：只按工具名判高危会漏掉改金额的写操作——律师有权改自己
案件的金额，误改就是事故。真实注册表里 `update_case{target_amount}`、
`update_reminder{due_at}`、`create_contract{fixed_amount}` 等命中
`SENSITIVE_ARG_MARKERS`（金额 / 期限 / 状态）后升级为需审批。

四张清单（`DANGER_PATTERNS` / `CRITICAL_PATTERNS` / `SENSITIVE_ARG_MARKERS` /
`WRITE_PREFIXES`）在 Python 与 `approval-gate.ts` 之间**逐项同步**，并有
parity 单测守护；对 mcp_server 实际注册表（410 个工具，2026-10-25 补注册
workflow 模板管理 10 件后）的覆盖由
`test_agent_risk_tiers.py` 对账（新增 `delete_xxx` 忘进审批即红灯，读类被误拦也红灯）。
`approve_` 亦属高危：`approve_workflow_step` 是工作流 gate 的人工确认动作
本身，模型低危直调 = 替人批准自己发起的工作流（详见 DANGER_PATTERNS 注释）。

### fail-closed 与离线审批

只有 `status=approved` 放行。超时 / 网络失败 / 链路异常一律拒绝。

**但「无人可问」不再等于「直接拒绝」**：任务式后台运行本来就没有 SSE 连接，
一律拒绝会把那条路彻底判死。现按「有没有人在线」分流：

| 情形 | 行为 |
|:-|:-|
| 完全无人在线（任务式后台） | 保持 `pending` 挂起，等用户回来在会话里看到待审批卡片再决定（`FACHUAN_APPROVAL_OFFLINE`，默认开，上限 `OFFLINE_TIMEOUT=7200s`） |
| 有人在别的 worker 连着却送不到 | 链路异常 → 仍拒绝 |
| 离线也超时没人管 | `timeout` → 拒绝（绝不默默放行） |
| `FACHUAN_APPROVAL_OFFLINE=0` | 回到原行为：无人可问即拒绝（保守部署用） |

用户回来通过 `GET /approvals/pending` 拿到待审批列表，`POST /approval/{id}/decide`
决定后，原本阻塞的工具调用继续执行。

**为什么审批必须走 `event_bus.publish`**：审批走独立 HTTP 回调，与「发起对话的
SSE 连接」不在同一调用栈。早期实现是「自己 `register` 一个队列再 `put`」——
那会与 `chat_service` 的 SSE 循环各持一个队列，事件永远送不到前端（表现为
审批必定超时）。必须 `publish` 到总线，送给真实订阅者。

### 跨 worker 分发（Redis）

生产是多 worker 部署：**审批回调可能落在 worker A，而用户的 SSE 连接在 worker B**。
只用进程内队列时事件送不到前端。因此总线分两层：

```
publish(session_id, event)
  ├─ 直接投递给本进程订阅者（快路径，同 worker 零开销）
  └─ 写入 Redis list（供其他 worker 消费）

每个 worker 一个 relay 协程：
  while True: 从 Redis list 弹出 → 投递给本进程订阅者
```

- **无 Redis 时自动退化为纯进程内**，开发环境行为不变
- 事件带 `_origin` 标记，本进程发过的不重复投递（避免双发）
- list 有长度上限与 TTL，无人消费时不会无限堆积

实测：worker A 订阅、worker B 发布，A 能收到 `approval_request`（B 侧本地送达数为 0）。

## 5. 端点

前缀 `/api/v1/agent`：

| 方法 | 路径 | 说明 |
|:-|:-|:-|
| POST | `/sessions` | 新建会话（可带 `origin` / `case_id` / `contract_id`） |
| GET | `/sessions` | 列出会话（可按 `origin` / `case_id` / `contract_id` 过滤，归属恒按当前用户） |
| GET | `/sessions/{id}` | 会话详情 |
| GET | `/sessions/{id}/messages` | 消息历史（旧→新，重开会话回放） |
| PATCH | `/sessions/{id}` | 重命名 |
| DELETE | `/sessions/{id}` | 删除会话（级联清理 pi session 上下文） |
| POST | `/sessions/{id}/messages` | 发消息（SSE 流） |
| POST | `/tasks` | **提交后台任务**（立即返回 task_id，跑完通知） |
| GET | `/tasks/{id}` | 查询后台任务进度 |
| POST | `/sessions/{id}/steer` | **运行中插话**（工具调用后、下次模型调用前生效） |
| POST | `/sessions/{id}/follow-up` | **追加一轮**（agent 干完当前所有活后再跑） |
| DELETE | `/sessions/{id}/queue` | 撤回已排队未生效的插话 / 追加，返回原文 |
| POST | `/approval/request` | **pi extension 回调**（`X-Internal-Token` 鉴权） |
| POST | `/approval/{id}/decide` | 前端提交审批决定 |
| GET | `/approvals` | 审批记录（审计，含 `risk_level`） |
| GET | `/approvals/pending` | **待审批列表**（离线审批入口） |
| GET | `/usage` | 成本/耗时汇总（token、工具调用数、失败率、平均耗时） |
| GET | `/usage/daily` | 按天趋势 |
| GET | `/usage/by-model` | 按模型分布 |

### 运行中插话（steer / follow_up）

用户不必「停止 → 重发完整需求 → 前功尽弃」。`services/live_sessions.py` 维护
进程内 `session_id → PiRpcSession` 表：

```
stream_chat 进入   → register(session_id, pi_session)
POST /steer        → get(session_id) → pi_session.steer(msg)
stream_chat 退出   → unregister(session_id, pi_session)
```

`PiRpcSession` 持有真实子进程管道、**无法跨进程传递**，所以插话请求必须落到
「跑着这个会话的 worker」才生效。这与审批相反（审批走 Redis 是因为 SSE 与回调
可能不同 worker）。跨 worker 时如实返回 409「没有运行中的对话」，绝不假装成功。
同一会话同时只允许一个运行中的进程（`SessionBusyError`），否则模型会看到两份
互相冲突的上下文。

### 多入口（origin）

`AgentSession.origin`：`chat`（对话页）/ `case`（案件内）/ `contract`（合同内）/
`task`（任务式后台）。配合 `case_id` / `contract_id` 支持「列出本案所有 AI 会话」。

`case_id` **不加外键**（避免 agent 因业务表被删而丢审计记录，也避免跨 app 迁移
依赖）；**归属校验始终以 `user` 为准**——`case_id` 只用来再缩小范围，传别人的
`case_id` 看不到任何数据。

### 任务式（后台）入口

对话式要求「人开着页面盯着」；律师的真实场景常常是「这个案子帮我把材料梳理
一遍」——要跑几分钟，人不可能一直等。`POST /tasks` 专门服务这类活：

```
POST /tasks {message, title?, case_id?}
  └─ 建 origin=task 会话（task_state=queued）
       └─ django-q 入队 run_agent_task
            ├─ task_state=running
            ├─ 复用 stream_chat 抽干事件流（审批/成本/落库全都走上同一条路径）
            └─ 跑完 → task_state=succeeded|failed + task_finished_at + 通知消息
```

| 关注点 | 做法 |
|:-|:-|
| 要不要另写一套编排 | **不**。后台与前台复用 `stream_chat`，否则审批漏判、`AgentRun` 漏记这些坑要再踩一遍 |
| 高危工具怎么办 | 没有 SSE 连接 → 走离线审批挂起（见 §4），用户回来从 `GET /approvals/pending` 处理 |
| 跑完怎么知道 | 写入一条 `metadata.kind=task_notification` 的助手消息（会话列表/回放里直接可见），并把 `notified` 置真；不引入新通知表，也不要求用户在线 |
| 失败会卡住吗 | 不会。所有异常收口成 `task_state=failed` + 人话 `task_error`（不含堆栈），且通知失败不会把已成功任务改判失败 |
| 进度怎么查 | `GET /tasks/{id}` 或 `GET /sessions` 里读 `task_state` |

### 成本可观测（AgentRun）

`AgentRun` 一轮一行：`model` / `status`（ok·error·cancelled）/ `input_tokens` /
`output_tokens` / `tool_calls` / `duration_ms` / `error_kind`。

**取消与出错也记录**——只记成功等于把最贵的失败藏起来：用户按停止时模型可能已
跑了大量 token，网关超时重试也是真金白银。`error_kind` 存短码
（`pi_unavailable` / `queue_timeout` / `pi_error` / `unexpected`），既可聚合又不
泄露内部细节。`AgentMessage.metadata.output_tokens` 是逐条消息的，回答不了
「这个律师本月花了多少」，所以另立一表。Django Admin 提供只读视图（`AgentRunAdmin`）。

## 5.1 联调中磨平的坑（都是真踩过的）

这几处不看会踩，都已修复并有回归测试：

| 现象 | 根因 | 修法 |
|:-|:-|:-|
| SSE 返回 0 字节 | 生成器 `finally` 里 `yield`，客户端断开时抛 `RuntimeError` | `done` 移到正常路径，`finally` 只清理 |
| SSE 返回 0 字节 | 异步上下文里调同步 `.update()` | 改 `aupdate()` |
| MCP 完全不加载 | 项目级 `.pi/mcp.json` 需项目信任，RPC 模式无法弹信任提示 | 配置写到用户级，用 `PI_CODING_AGENT_DIR` 指向 |
| 独立目录丢凭证 | `PI_CODING_AGENT_DIR` 隔离了 `~/.pi/agent` | 优先从 `LLMProvider` 渲染 models.json；渲染不出才复制用户级凭证 |
| 只有 activity、无 delta | 双队列用「两个 get task + `asyncio.wait`」，取消时丢掉已取出的事件 | 改为单循环迭代 + 审批事件非阻塞轮插 |
| **稳定 `Connection error` + 重试 3 次** | **Django 继承了开发机的 `HTTP_PROXY`，而内网 LLM 网关（152.x）不在 `NO_PROXY` 里，pi 走代理绕死** | `_clean_env()` 剔除全部代理变量 |
| 同一段文本推两次 | `message_update` 的 delta 与 `message_end` 的全文重叠 | `DeltaTracker.note()` 推高水位，全文走 `diff()` |
| `--model` 解析不到 | `_resolve_model()` 走同步 ORM，异步上下文抛 `SynchronousOnlyOperation` 被吞 | 改 async + `sync_to_async`；`write_pi_config` 同样处理 |

> 最后一类问题最阴——curl 能通、pi 单独能通，只有「Django 起的 pi」不通。
> 以后再遇到「pi 连不上模型」，先查 `env | grep -i proxy`。

## 6. 事件契约

```
meta → activity(thinking|queued)? → delta*/thinking* → tool_call* → tool_result*
     → usage* → approval_request? → error? → done
```

| 事件 | 关键字段 |
|:-|:-|
| `meta` | `session_id` / `agent` |
| `activity` | `status`（`thinking` / `queued`）；queued 时带 `position`（前方人数） |
| `delta` | `content`（正文增量） |
| `thinking` | `content`（思考增量，不推高正文水位） |
| `tool_call` | `tool_call_id` / `name` / `arguments` |
| `tool_result` | `tool_call_id` / `name` / `result`（纯文本，≤2000 字）/ `is_error` |
| `usage` | `input_tokens` / `output_tokens` |
| `approval_request` | `approval_id` / `tool_name` / `tool_args` / `risk_level` / `needs_second_confirmation` |
| `error` | `message`（已翻译成人话，不吐堆栈） |
| `done` | `session_id` |

`usage` 携带 pi 的精确计数（工具循环里每段 assistant 各发一次），前端流式期间
用估算展示实时 tok/s、结束后用真实值收尾；累计值落在 `AgentRun` 与助手消息
`metadata.output_tokens`。

### 翻译规则（1.4.0，全部有真实 fixture 兜底）

`pi/bridge.py` 是唯一翻译层，`tests/ci/fixtures/agent/*.jsonl` 是真机录制的
1.4.0 事件流（含纯文本与带工具调用两份）。三条纪律：

1. **正文只认 `text_delta`**；`text_end`/`message_end` 的全文只用于校正差额，
   不重复发（`DeltaTracker` 水位）。
2. **`toolcall_delta` 是参数 JSON 片段，绝不当正文发**——曾把 `{"path": "`
   混进用户看到的回答里。
3. **工具调用/结果各只发一次**：`toolcall_end` / `tool_execution_end` 为准，
   `tool_execution_start` 与 `message_end` 只补发尚未告知的。

## 6.1 版本敏感面已实测校正（1.4.0）

1.3.0 时代 README 写的是「`message_update` 带 message 快照，靠与 `message_end`
求差去重」。**1.4.0 已改成 delta-only**（`docs/json.md`），并新增
`text_start`/`text_end`/`toolcall_start`/`toolcall_delta`/`toolcall_end` 全套
分块事件。旧代码在 1.4.0 下会：把参数 JSON 当正文推给前端、tool_call 双发、
工具结果泄成 Python repr（`{'content': [...]}`）、`toolResult` 角色完全认不出
（它在 1.3 叫 `tool`）。全部已修并有 fixture 测试。

## 7. 配置

| 环境变量 | 默认 | 说明 |
|:-|:-|:-|
| `FACHUAN_PI_BIN` | `which pi` | pi 可执行文件 |
| `FACHUAN_PI_MODEL` / `FACHUAN_PI_PROVIDER` | — | 透传 `pi --model/--provider` |
| `FACHUAN_PI_APPROVAL_EXTENSION` | 内置路径 | 审批 extension |
| `FACHUAN_PI_AGENTS_PATH` | 内置 `pi/AGENTS.md` | 系统提示词模板路径 |
| `FACHUAN_APPROVAL_URL` | `127.0.0.1:8002/api/v1/agent/approval/request` | 审批端点 |
| `FACHUAN_INTERNAL_TOKEN` | 空 | 服务间鉴权（**生产必须配置**） |
| `FACHUAN_AGENT_POOL_SIZE` | 4 | 进程池容量（1–32） |
| `FACHUAN_AGENT_QUEUE_TIMEOUT` | 60 | 排队上限（秒），0 表示不限 |
| `FACHUAN_AGENT_HOME` | `~/.fachuan-agent` | **稳定根目录**（work / config / sessions），权限 0700 |
| `FACHUAN_APPROVAL_OFFLINE` | 1 | 无人在线时是否挂起等离线审批；`0` 回到「无人可问即拒绝」 |
| `FACHUAN_MCP_SHARED` | 1 | 共享 MCP 开关 |
| `FACHUAN_MCP_HTTP_PORT` | 8011 | 共享 MCP 端口 |

### 生产部署的两条新增要求

1. **`FACHUAN_AGENT_HOME` 必须被所有 worker 共享**（NFS / 挂载卷）——
   否则同一会话落到不同 worker 时会看到两段互不相干的历史。单机多 worker 天然满足。
2. **目录权限 0700、`models.json` 0600**（代码已做，但要确认共享卷不放开权限）。

## 8. 部署前置：pi 的安装、升级与回滚

**已验证版本：1.4.0。** RPC 协议、事件翻译、扩展钩子、session/compaction 均按
此版本实测开发，事件形态由真机录制的 fixture（`tests/ci/fixtures/agent/`）校准。
升级前先看下方「版本敏感面」。

### 安装（首次）

两种官方安装方式：

```bash
# 方式一：官方 installer（推荐）——依赖全部锁版、自带 Node、旧版本保留可即时回滚
curl -fsSL https://pi.dev/install.sh | sh

# 方式二：npm——需要系统已有 Node.js ≥ 22.19，且不锁传递依赖
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

安装后 `pi --version` 必须与「已验证版本」一致。**不要装最新版直接用**——
本 app 对 pi 的事件形态有实测假设（见「版本敏感面」），新版需先冒烟。

| | installer（managed install） | npm -g |
|:-|:-|:-|
| 安装位置 | `~/.pi/agent/install/releases/<版本>/` | npm 全局目录 |
| 版本选择 | launcher 按 `install/current-version` 指针选 | 单版本覆盖 |
| 旧版本 | **保留**，回滚即时 | 不保留，回滚需重装 |
| Node | 自带（`~/.local/share/pi-node`） | 依赖系统 Node |

**生产建议用 installer，并用 `FACHUAN_PI_BIN` 钉到具体 release 路径**：

```bash
# backend/.env
FACHUAN_PI_BIN=/home/<user>/.pi/agent/install/releases/1.4.0/node_modules/.bin/pi
```

钉死后，即使有人在机器上跑了 `pi update`（只改 current-version 指针），本 app
用的仍是锁定版本——升级变成「显式改环境变量 + 冒烟」的受控动作，而不是被动漂移。
这是引入 pi 的主要部署成本（`tool_call` 钩子只能用 TypeScript 写）。

### 升级步骤

pi 更新是手动触发的（无自动升级机制）：

1. **读上游变更**：新版本随包文档在
   `~/.pi/agent/install/releases/<新版本>/node_modules/@earendil-works/pi-coding-agent/docs/`，
   与 1.4.0 对比 `rpc.md`、`rpc-commands.md`、`json.md`、`extensions.md`、`cli.md`、
   `compaction.md`，按「版本敏感面」逐项核对。
2. **升级**：`pi update`（installer 安装）；npm 安装则
   `npm install -g @earendil-works/pi-coding-agent@<版本>`。
3. **重启 Django**：进程池是进程级单例，池内空闲 pi 子进程会一直跑旧版本，
   重启后新建的进程才是新版。共享 MCP（Python 进程）不受影响。
4. **冒烟**（放开流量前必做）：
   - 真发一条消息，确认事件形态仍符合 `bridge.py` 的假设（`message_end` 带全文、
     `agent_settled` 到达）——**单测喂的是合成事件，拦不住上游改事件形态，这一步只能真机做**；
   - 真触发一次高危工具（如 `delete_case`），确认审批弹窗出现——这是在验证
     `approval-gate.ts` 在新版 pi 下加载成功（加载失败不会报错，见下表）；
   - 跑 `pytest tests/ci/unit/agent/`。
5. 通过后更新本节「已验证版本」与 `FACHUAN_PI_BIN`，重启。

### 版本敏感面（升级前必查）

| 耦合面 | 代码位置 | 变化时的表现 |
|:-|:-|:-|
| RPC 事件形态（`message_update` 是 delta-only；`text_end` 带 `content`；`toolcall_delta` 是参数碎片；工具结果角色叫 `toolResult`） | `pi/bridge.py` | 认错字段 → 参数 JSON 混入正文 / tool_call 双发 / 结果泄成 Python repr。**用真机 fixture 校准，别手写合成事件** |
| 扩展钩子 API（`tool_call` 返回 `{block:true}`） | `pi/approval-gate.ts` | 扩展加载失败 = **审批闸门静默消失**（`rpc_client.py` 只检查文件存在，缺失时 warning 后继续），只能真机触发审批验证 |
| CLI 参数（`--mode rpc --session-dir --session-id --approve --tools`） | `pi/rpc_client.py` | 参数改名 → 进程起不来（炸得响，反而安全）；`--session-id` 语义变化 → 会话失忆 |
| session 隔离维度（按 cwd 分 project） | `pi/session_store.py` | 改为按 id 全局查找 → 不同用户的会话可能串（必须回归「同一 id 换 cwd 不共享」） |
| `steer` / `follow_up` / `clear_queue` 命令 | `pi/rpc_client.py` | 命令改名 → 插话静默失效（返回 409 而非崩溃） |
| 配置文件 schema（`models.json` providers 结构、`mcp.json`、`PI_CODING_AGENT_DIR`） | `pi/model_config.py`、`pi/shared_mcp.py` | 报「No API key found」或 MCP 连不上，离根因很远 |
| 捆绑 Node 版本 | installer 自带 | `pi update` 可能连 Node 一起升 |

### 回滚

installer 安装的旧版本不删除，回滚即时：

```bash
echo 1.4.0 > ~/.pi/agent/install/current-version   # 或把 FACHUAN_PI_BIN 指回旧 release
# 然后重启 Django
```

npm 安装无版本保留：`npm install -g @earendil-works/pi-coding-agent@1.4.0`。

### 共享 MCP 无需手动启动

应用首次用到 agent 时自动检测并拉起共享 MCP（已在跑则复用）。
日常运维统一走根目录 Makefile（实现：`scripts/shared_mcp.sh`）：

```bash
make mcp          # 重启（杀旧拉新 + 工具面核对；改了 mcp_server 工具后必跑）
make mcp-verify   # 只核对：线上工具面 vs 代码注册表（MCP 真握手，非端口探测）
make mcp-status   # 进程 / 端口 / 运行时长 / 日志路径
make mcp-logs     # 跟随日志
```

`verify` 会逐名对比「运行中的工具面」与「代码注册表」：改了工具忘重启时
能直接点名缺失项，端口被非 MCP 进程占用时也会握手失败报错（这种情况下
Django 的自动拉起只探端口、会静默"复用"占用者，是已知边界）。

如需独立托管（例如拆到另一台机器），手动启动后把 pi 指过去：

```bash
FACHUAN_MCP_TRANSPORT=streamable-http FACHUAN_MCP_HTTP_PORT=8011 \
  python -m mcp_server
```

### 生产必须配的两项

```bash
# 审批回调的服务间鉴权（不配会警告，且回调不鉴权）
FACHUAN_INTERNAL_TOKEN=<长随机串>

# 审批端点（extension 回调地址，按实际部署域名/端口）
FACHUAN_APPROVAL_URL=https://<host>/api/v1/agent/approval/request
```

### 代理注意事项

`_clean_env()` 会剔除 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`（含小写）。
**如果 LLM 网关确实需要走代理**，不要改这个行为，而是把网关域名加入
`NO_PROXY` 后自行调整 `_clean_env`——否则会出现「curl 能通、pi 报
Connection error」的诡异现象。

## 9. 目录结构

```
apps/agent/
├── apps.py
├── admin.py                 # AgentRun（只读成本视图）/ AgentSession / AgentApproval
├── models/agent.py          # AgentSession / AgentMessage / AgentApproval / AgentRun
├── api/agent_api.py         # 会话、对话、插话、审批、用量端点
├── services/
│   ├── chat_service.py      # 对话编排（steer 接入点 + 消息/运行记录落库）
│   ├── history.py           # transcript 渲染（仅 pi session 缺失时的一次性回退）
│   ├── live_sessions.py     # 运行中会话表（session_id → PiRpcSession）
│   ├── session_service.py   # 会话 CRUD + 归属过滤（origin/case 维度）
│   ├── session_cleanup.py   # Django 会话 ↔ pi session 生命周期对齐
│   ├── usage_stats.py       # 成本/耗时聚合（summarize / daily / by_model）
│   ├── approval.py          # 风险分级 + 阻塞等待 + 离线审批
│   └── event_bus.py         # 按会话分发事件（进程内 + Redis 跨 worker）
├── pi/
│   ├── rpc_client.py        # RPC 协议（二进制按 LF 切分）+ steer/follow_up/abort
│   ├── pool.py              # 并发闸门（排队可见 + 排队超时 + 取消时 abort）
│   ├── bridge.py            # pi 事件 → 前端事件（1.4.0 delta-only）
│   ├── session_store.py     # 稳定目录布局（work/config/sessions）+ 清理
│   ├── shared_mcp.py        # 共享 MCP 管理
│   ├── model_config.py      # 从 LLMProvider 渲染 pi 的 models.json
│   ├── user_token.py        # 按律师身份铸 token（confused deputy 修复）
│   ├── AGENTS.md            # 系统提示词模板（pi 无条件读取工作目录的该文件）
│   └── approval-gate.ts     # pi 侧审批 extension（与后端分级同序）
└── migrations/
```

测试（`backend/tests/`）：

```
ci/unit/agent/
├── test_agent_runtime.py        # 翻译 / 审批兜底 / 总线 / abort / pool 取消接线
├── test_agent_bridge_fixture.py # 真机 1.4.0 事件流驱动（防上游改形态）
├── test_agent_live_sessions.py  # 运行中会话表 + steer/follow_up/clear_queue
├── test_agent_pool_queue.py     # 排队位置 / 排队超时 / 不泄漏信号量
├── test_agent_risk_tiers.py     # 四级分级 + 四表 parity + 395 工具注册表对账
├── test_agent_session_store.py  # 稳定目录 / 按会话定位 / 删会话级联 / 无凭证落盘
├── test_agent_multi_entry.py    # origin+case 过滤 / 离线审批 / 待审发现
├── test_agent_usage.py          # AgentRun 三态落库 + 聚合口径
├── test_agent_identity.py       # 凭证铸造 / env 配线 / 取消保文本
└── test_model_config.py
ci/fixtures/agent/*.jsonl        # 真机录制（已脱敏）
ci/integration/test_agent_api.py # 端点级：归属 / SSE 错误路径 / 审批 / 插话 / 用量
```

## 10. 验证状态

| 项 | 状态 |
|:-|:-|
| 单元测试（`tests/ci/unit/agent/`，10 个文件） | ✅ **170 passed** |
| 端点级集成测试（`tests/ci/integration/test_agent_api.py`） | ✅ **19 passed** |
| **bridge 对齐 1.4.0**（真机录制 fixture 驱动） | ✅ 正文无丢字/无重复；参数 JSON 不再混入正文；tool_call/result 各只发一次；工具结果为纯文本 |
| **停止真中止**（clear_queue + abort） | ✅ 取消分支 `close(abort_running=True)`，pool 接线有端到端测试 |
| **steer / follow_up / clear_queue** | ✅ 运行期登记 → 投递到同一进程；跨 worker 如实 409 |
| **排队可见 + 超时** | ✅ 位置递增 1,2；计数归零；超时抛可读错误且不泄漏信号量 |
| **成本可观测（AgentRun）** | ✅ ok/error/cancelled 三态落库；`/usage`、`/usage/daily`、`/usage/by-model` |
| **风险分级** | ✅ 四级判定；四表 parity；395 工具注册表对账；读类不误拦 |
| **pi 原生 session（上下文归 pi）** | ✅ 真机 12 轮仍准确记得首轮（`RECALL='收到1'`），input token 全程 20–66 不随轮次膨胀；会话 `517d5b20…` 单文件 27 条 message 记录，`AgentRun` 13 行 |
| **会话级联清理 + 越权防护** | ✅ 删会话连带清 pi 上下文；`user_id=None` 不匹配任何会话 |
| **多入口 + 离线审批** | ✅ origin/case 过滤且越权不可见；无订阅者 → pending 而非 rejected，决定后工具继续 |
| **审批拦截 + fail-closed** | ✅ `delete_case` 被拦；超时/链路异常拒绝；`FACHUAN_APPROVAL_OFFLINE=0` 可回退 |

### 真机端到端冒烟（1.4.0 + 真实 LLM kimi-2.6，实测记录）

| 场景 | 实测结果 |
|:-|:-|
| 真实对话 + 工具调用 | ✅ 调用 `get_current_user` 成功返回真实用户名；事件序列 `meta→activity→delta→usage→done` 无重复；`AgentRun` = `ok/kimi-2.6/54374in/36out/1 tool/18386ms`；session 文件按 UUID 落盘 |
| 真实审批拦截 | ✅ `delete_reminder` 判为 `high` → 建 pending → 无人在线且关闭离线审批 → `timeout` 拒绝，工具未执行；模型如实回报「用户拒绝了」，未编造执行结果；审批记录 `risk_level=high` 落库 |
| 真机 steer | ✅ 运行期 `is_live=True`；插话返回 `queued`；正文末尾出现被注入的那句话（模型从长篇论述切到遵循指令）；结束后 `is_live=False` |
| 工具面完整性 | ✅ pi 侧 **395 tools = 注册表 395**，差集 0 |

> 排查记录：冒烟初期发现 pi 只看到 378 个工具（缺 `get_current_user` 等 22 个），
> 根因是**共享 MCP 进程跑了旧代码**（进程启动于工具新增之前），重启后即 395/395。
> 结论：**更新 `mcp_server` 工具后必须重启共享 MCP**，否则 pi 拿到的工具面是旧的
> （这种不一致不会有明显报错，只会表现为「模型说没有这个工具」）。
| **内置工具已禁用**（`--tools mcp__fachuan__*`，bash/edit/write 不再声明） | ✅ 参数握手验证 |
| ruff check / format | ✅ |
| Django `manage.py check` | ✅ 0 issues |
| RPC 真实对话（HTTP 端到端） | ✅ 输出「联调OK」，delta 无重复 |
| MCP 378 工具（共享 HTTP） | ✅ `fachuan: connected, 378 tools` |
| 8 并发（共享 MCP，旧池化复用口径） | ✅ 3.4s / 71MB |
| **每请求进程架构延迟（真实 LLM kimi-2.6，含 --tools/AGENTS.md/MCP 共享）** | ✅ 串行单轮 0.8–1.5s；4 路并发总 1.93s（单路 1.4–1.9s）；进程 spawn 本身 <0.05s |
| **审批同意路径** | ✅ 订阅者收到 `approval_request` → 同意 → 工具放行 |
| **跨 worker 分发（Redis）** | ✅ worker A 订阅、worker B 发布，A 能收到事件 |
| 共享 MCP 自动拉起 | ✅ 未运行时自动启动，已运行则复用 |
