# mcp_server —— 法穿 AI Copilot 的工具面

> 409 个 MCP 工具（2026-10-25），streamable-http :8011 共享一份常驻进程，
> 服务 `apps/agent` 的 pi 会话；也可 stdio 单进程跑（开发/手工）。

## 架构速览

```
pi 会话(每律师一个) ──Bearer 当前律师token──▶ RequestAuthMiddleware(ASGI)
                                                    │ ContextVar 存 Authorization
                                                    ▼
                                        FastMCP(MCPServer "法穿SI Copilot")
                                                    │ 409 工具(server.py 注册)
                    ┌───────────────────────────────┼──────────────────────┐
                    ▼                               ▼                      ▼
            REST 透传型工具(绝大多数)         直接 ORM 工具(workflow 15 个)  纯本地工具
            client.py → 后端 REST API          apps/workflow/mcp/          get_server_time 等
            (透传 Bearer,以律师身份)           (_resolve_mcp_access 重建身份)
```

## 关键机制（都有单测守护）

| 机制 | 文件 | 要点 |
|---|---|---|
| 身份透传 | `identity.py` | ASGI 中间件把 Authorization 头存 ContextVar;`client._headers()` 优先透传 → 工具以**当前律师**身份调 REST(归属过滤/权限/审计与本人登录一致)。无透传(stdio)回退服务账号。双律师并发实测无串扰 |
| 错误直达模型 | `client.py` | `FachuanApiError(ToolError)`:非 2xx 的 HTTP 状态 + 后端 detail 完整回传(is_error=true),模型可自纠;消息保持 `"HTTP <status>:"` 前缀(agent_attachments 分类依赖) |
| 传输层翻译 | `client.py` | `_guard_transport` 把超时/断连翻成 `FachuanTransportError`(可读原因+重试指引);GET 幂等自动重试一次(传输故障/502/503/504),非幂等方法不重试 |
| 下载闸门 | `client.py` | `download()` 1MB 上限(env `FACHUAN_MCP_MAX_DOWNLOAD_MB`),防 base64 挤爆会话上下文;所有 b64encode 输出必须经它(`TestClientAbstractionBoundary` 禁止 `client._http` 直连) |
| LLM 链路超时 | `tools/documents/*.py` | 生成类工具 client 侧 `timeout=180`;**pi 侧 mcp.json `timeout: 200` 必须更大**(`apps/agent/pi/shared_mcp.py`,双端失配则 180 作废) |
| workflow 身份链 | `apps/workflow/mcp/workflow_tools.py` | 直 ORM 工具用 `_resolve_mcp_access` 从 ContextVar Bearer 重建律师+org_access;`_mcp_guard_run_access` 补 run 案件访问校验;模板管理 `_require_admin` fail-closed;`server.py:_workflow_tool` 统一剥离 user 参数 + 把 BusinessException/DoesNotExist 翻成 ToolError |
| 审批联动 | `apps/agent/services/approval.py` | pi 侧按工具名模式(delete/send_/submit_/confirm_/**approve_**/…)判高危;MCP 工具面新增删除类工具会被 `delete` 模式自动覆盖,新增其他危险前缀需同步双表 |

## 运维

```bash
make mcp           # 重启共享 MCP + 工具面核对(改了 mcp_server/** 后必须)
make mcp-verify    # 只核对线上工具面 vs 代码注册表
make mcp-status    # 进程/日志
```

**改了工具代码不重启 = 模型拿到的仍是旧工具面,且无任何报错**（详见根 CLAUDE.md 避坑指南）。

## 工具注册纪律

- 新工具写在 `tools/<域>/`,在 `tools/__init__.py` re-export,在 `server.py` `mcp.tool()(...)` 注册——**三处缺一都会静默丢工具**(`tests/ci/unit/mcp_server/test_tool_registration.py` 与 `test_server_registration.py` 会拦)。
- 直接 ORM 的工具(不经 REST)放 `apps/<域>/mcp/`,注册时用 `_workflow_tool` 包装(参数剥离+异常翻译),并**必须**处理身份(ContextVar Bearer → 律师),否则退化为服务账号语义。
- `**kwargs`/`**extra` 形参会被 FastMCP 编译成必填 object 参数,禁用;可选聚合参数用 `dict | None`。

## 测试金字塔（tests/ci/unit/mcp_server/）

| 层 | 文件 | 覆盖 |
|---|---|---|
| 注册完整性 | `test_tool_registration.py` / `test_server_registration.py` | 定义↔注册对账、基线 409、docstring/注解、白名单防退化 |
| 路径契约 | `test_rest_path_contract.py` | AST 全扫 client 调用 vs OpenAPI,防 REST 路径漂移 |
| 参数契约 | `test_rest_param_contract.py` | 工具转发的参数必须被端点声明——ninja 静默忽略未声明参数=「从未生效」的假参数(两轮审计共 17 处实锤,含 create_lawyer/update_lawyer/update_doc_converter 三个「从未成功过」的 multipart 形状错拼);收集器覆盖字面量/变量字典/f-string 路径(含 /api/v1 前缀)/内联与 anyOf schema;裸 payload 端点 allowlist 禁止新增 |
| 投影契约 | `test_projection_fields.py` | 默认投影列出的字段必须存在于 API items schema——project 按键挑选不报错,列了不存在的字段=模型点名要也静默落空 |
| docstring 枚举值 | 无自动门禁(review 把关) | 文档宣称的取值必须对照模型 TextChoices——filter 对错值静默空列表、裸 CharField 对错值静默落库(2026-10-25 审计 13 处:case_type 假枚举/fee_mode 小写绕过金额校验/中文代理阶段必炸/running≠in_progress/site_name 死路示例) |
| 失败语义 | `test_error_semantics.py` | 公共工具函数禁止 `except Exception` 吞异常——FachuanApiError/FachuanTransportError 是 ToolError 子类,必须穿透成 `isError: true`;吞成 `{"success": False}` 伪正常结果会让模型得出假事实结论(2026-10-25 审计 enterprise_data 8 处)。私有 helper 的批量部分失败聚合豁免(folder_file/web_search 形态) |
| ToolAnnotations | `test_tool_annotations.py` | `readOnlyHint`/`destructiveHint` 从审批分层权威表(approval.classify_risk)机械推导,注册统一走 `_t` 装饰器——禁裸 `mcp.tool()`(绕过 `_t` 即绕过推导);线上三分 409=226 只读+69 销毁/高危+114 普通写 |
| 客户端行为 | `test_client.py` | token 刷新、错误信封、传输韧性、下载闸门、巨型列表护栏、抽象边界 |
| 工具行为 | `test_new_tools.py` / `test_agent_attachments.py` / `test_fetch_url.py`(含 SSRF 拦截) / … | 重组型工具的真实逻辑 |

跑法:`DB_NAME=test_fachuan_dev .venv/bin/pytest tests/ci/unit/mcp_server/ -q --reuse-db`(严禁不带 DB_NAME)。

## 并发与审计（2026-10-25 验证）

- **事件循环不阻塞**：工具几乎全是同步 `def`,MCPServer 对同步函数走
  `anyio.to_thread.run_sync`(worker 线程);唯一 async 工具 `web_search` 已把
  阻塞的 httpx 调用 `run_in_executor` 委派。一个 180s 的 LLM 工具不会卡住其他会话。
- **每次工具调用都有审计痕**:pi 侧 `tool_result` 事件逐条落 `AgentMessage`
  (role=TOOL,工具名+结果[:8000]+时间);完整参数在 pi session 文件
  (`FACHUAN_AGENT_HOME`);高危另有 `AgentApproval.tool_args`。
  MEDIUM 级「静默留痕」的承诺由此兑现,不依赖 logs/api.log 轮转。
- **审批 extension 每请求新进程加载**:pi 进程每请求一造(见 `pool.py`),
  不复用——approval-gate.ts 的模式表更新后,下一个请求立即生效,无存量进程窗口。

## 已知规模事实（灰度决策依据）

- 409 工具 `tools/list` ≈ 257KB ≈ **8.8 万 token** 常驻上下文(direct 模式),靠 prompt cache 摊薄。
- 灰度开关 `FACHUAN_MCP_EXPOSURE`(deferred/codemode/hidden)与 per-tool `toolExposure` 混合面备选见 `apps/agent/pi/shared_mcp.py` 注释;deferred 的代价是 OpenAI 兼容网关丢 prompt cache(pi #10940)。
