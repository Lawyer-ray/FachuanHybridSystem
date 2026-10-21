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

因此 `pool.acquire()` 每次渲染配置 → 起新进程 → 用完销毁**并删除临时目录**
（目录里的 models.json 含真实 API key，不允许在磁盘上堆积）；「池」的作用
退化为限制并发数（`FACHUAN_AGENT_POOL_SIZE`，默认 4，上限 32）。

### 工具面：只声明 MCP 工具

pi 启动带 `--tools "mcp__fachuan__*"`，**内置的 read/bash/edit/write 全部不向模型
声明**——它们能以 Django 进程权限读写文件、执行命令，且不在审批清单内，是提示
注入直通服务器 RCE 的通道。审批 extension 缺失时进程拒绝启动（fail-closed）。

### 多轮对话与系统提示词

pi 每请求新进程、天然无记忆。多轮上下文由 `AgentMessage` 表持有：发送前把最近
历史经 `services/history.py` 渲染成 transcript 附在 prompt 前（超预算丢最旧），
本轮的助手文本与工具结果在流结束时回写该表。系统提示词是工作目录里的
`AGENTS.md`（pi 无条件读取，与项目信任无关），模板在本 app 内置，可用
`FACHUAN_PI_AGENTS_PATH` 覆盖。

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

**fail-closed**：只有 `status=approved` 放行。超时 / 网络失败 / 无 SSE 订阅者，
一律拒绝。

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
| POST | `/sessions` | 新建会话 |
| GET | `/sessions` | 列出会话 |
| DELETE | `/sessions/{id}` | 删除会话 |
| POST | `/sessions/{id}/messages` | 发消息（SSE 流） |
| POST | `/approval/request` | **pi extension 回调**（`X-Internal-Token` 鉴权） |
| POST | `/approval/{id}/decide` | 前端提交审批决定 |
| GET | `/approvals` | 审批记录（审计） |

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
meta → activity → delta* → tool_call*/tool_result* → approval_request? → error? → done
```

沿用原 `workbench` 时代定下的事件契约形态，前端对话组件按此契约渲染即可。

## 7. 配置

| 环境变量 | 默认 | 说明 |
|:-|:-|:-|
| `FACHUAN_PI_BIN` | `which pi` | pi 可执行文件 |
| `FACHUAN_PI_MODEL` / `FACHUAN_PI_PROVIDER` | — | 透传 `pi --model/--provider` |
| `FACHUAN_PI_APPROVAL_EXTENSION` | 内置路径 | 审批 extension |
| `FACHUAN_PI_AGENTS_PATH` | 内置 `pi/AGENTS.md` | 系统提示词模板路径 |
| `FACHUAN_APPROVAL_URL` | `127.0.0.1:8002/api/v1/agent/approval/request` | 审批端点 |
| `FACHUAN_INTERNAL_TOKEN` | 空 | 服务间鉴权（**生产必须配置**） |
| `FACHUAN_AGENT_POOL_SIZE` | 4 | 进程池容量 |
| `FACHUAN_MCP_SHARED` | 1 | 共享 MCP 开关 |
| `FACHUAN_MCP_HTTP_PORT` | 8011 | 共享 MCP 端口 |

## 8. 部署前置：pi 的安装、升级与回滚

**已验证版本：1.3.0。** RPC 协议、事件翻译、扩展钩子均按此版本实测开发，
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
FACHUAN_PI_BIN=/home/<user>/.pi/agent/install/releases/1.3.0/node_modules/.bin/pi
```

钉死后，即使有人在机器上跑了 `pi update`（只改 current-version 指针），本 app
用的仍是锁定版本——升级变成「显式改环境变量 + 冒烟」的受控动作，而不是被动漂移。
这是引入 pi 的主要部署成本（`tool_call` 钩子只能用 TypeScript 写）。

### 升级步骤

pi 更新是手动触发的（无自动升级机制）：

1. **读上游变更**：新版本随包文档在
   `~/.pi/agent/install/releases/<新版本>/node_modules/@earendil-works/pi-coding-agent/docs/`，
   与 1.3.0 对比 `rpc.md`、`json.md`、`extensions.md`、`cli.md`，按「版本敏感面」逐项核对。
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
| RPC 事件形态（`message_update` 只带 usage、全文在 `message_end`、toolCall 藏在 content 块） | `pi/bridge.py` | 上游改为真流式 delta → 双发或丢字，单测全绿但真机错 |
| 扩展钩子 API（`tool_call` 返回 `{block:true}`） | `pi/approval-gate.ts` | 扩展加载失败 = **审批闸门静默消失**（`rpc_client.py` 只检查文件存在，缺失时 warning 后继续），只能真机触发审批验证 |
| CLI 参数（`--mode rpc --no-session --approve`） | `pi/rpc_client.py` | 参数改名 → 进程起不来（炸得响，反而安全） |
| 配置文件 schema（`models.json` providers 结构、`mcp.json`、`PI_CODING_AGENT_DIR`） | `pi/model_config.py`、`pi/shared_mcp.py` | 报「No API key found」或 MCP 连不上，离根因很远 |
| 捆绑 Node 版本 | installer 自带 | `pi update` 可能连 Node 一起升 |

### 回滚

installer 安装的旧版本不删除，回滚即时：

```bash
echo 1.3.0 > ~/.pi/agent/install/current-version   # 或把 FACHUAN_PI_BIN 指回旧 release
# 然后重启 Django
```

npm 安装无版本保留：`npm install -g @earendil-works/pi-coding-agent@1.3.0`。

### 共享 MCP 无需手动启动

应用首次用到 agent 时自动检测并拉起共享 MCP（已在跑则复用）。
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
├── models/agent.py          # AgentSession / AgentMessage / AgentApproval
├── api/agent_api.py         # 会话、对话、审批端点
├── services/
│   ├── chat_service.py      # 对话编排（历史回放 + 消息落库）
│   ├── history.py           # 多轮 transcript 渲染（纯函数）
│   ├── approval.py          # 审批策略 + 阻塞等待
│   └── event_bus.py         # 按会话分发事件（进程内 + Redis 跨 worker）
├── pi/
│   ├── rpc_client.py        # RPC 协议（二进制按 LF 切分）
│   ├── pool.py              # 进程池
│   ├── bridge.py            # pi 事件 → 前端事件
│   ├── shared_mcp.py        # 共享 MCP 管理
│   ├── model_config.py      # 从 LLMProvider 渲染 pi 的 models.json
│   ├── AGENTS.md            # 系统提示词模板（pi 无条件读取工作目录的该文件）
│   └── approval-gate.ts     # pi 侧审批 extension
└── migrations/
```

## 10. 验证状态

| 项 | 状态 |
|:-|:-|
| 单元测试（翻译 / 审批 / 总线 / 共享 MCP / DeltaTracker / _clean_env / 工具限制 / transcript / AGENTS.md / 审批归属） | ✅ 39 passed |
| **内置工具已禁用**（`--tools mcp__fachuan__*`，bash/edit/write 不再声明） | ✅ 参数握手验证 |
| ruff check / format | ✅ |
| Django `manage.py check` | ✅ 0 issues |
| RPC 真实对话（HTTP 端到端） | ✅ 输出「联调OK」，delta 无重复 |
| MCP 378 工具（共享 HTTP） | ✅ `fachuan: connected, 378 tools` |
| 8 并发（共享 MCP） | ✅ 3.4s / 71MB |
| **审批拦截 + fail-closed** | ✅ `delete_case` 被拦，无订阅者时返回「用户拒绝了」 |
| **审批同意路径** | ✅ 订阅者收到 `approval_request` → 同意 → 工具放行 |
| **跨 worker 分发（Redis）** | ✅ worker A 订阅、worker B 发布，A 能收到事件 |
| 共享 MCP 自动拉起 | ✅ 未运行时自动启动，已运行则复用 |
