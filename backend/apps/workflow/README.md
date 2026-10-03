# ⚙️ 工作流引擎（workflow）

诉讼工作流引擎：模板（steps_schema JSON）驱动 Temporal DynamicWorkflow，把 MCP 工具、内部 Activity、LLM / HTTP / 代码 / 审批门编排为可执行流程。

## 功能概述

- 模板 CRUD（slug 唯一、分类 litigation/preservation/enforcement、temporal_workflow_name、steps_schema）——**仅管理员**可写；步骤白名单：`code` 类型全员封禁（受限沙箱可被逃逸），`http`/`mcp_tool`（含任意 type 步骤携带 `mcp_tool` 字段——执行器按字段分发）仅 superuser 可编排（v27.2.7 安全加固）
- **DynamicWorkflow 通用引擎**：8 种步骤类型（activity / gate / wait / condition / delay / llm / http / code），按 schema 顺序执行，支持条件跳转（goto_false / skip_next）、on_fail=skip|abort、`{{variable.path}}` 与 `previous_step.result.x` 模板变量
- activity 步骤双路由：有 `mcp_tool` → `execute_mcp_tool`（动态调用 mcp_server 里的同步工具函数）；否则查 INTERNAL_ACTIVITY_MAP 调内部 activity
- **人工审批 gate**：WorkflowRun 置 waiting_human，经审批信号恢复（gate 步骤配置 `signal_key` 时用对应命名信号，缺省通用 `gate_approved`，均按 data.step_id 路由）；wait 步骤复用同一信号机制并可超时
- 内部 Activity 覆盖证据分析链路：收集事实 → 列材料 → 单证据分析 → 汇总 → 建议排列 → 应用排列（写 CaseMaterialGroupOrder）→ 构建诉讼上下文 → 生成/审查起诉状 → 下载文书
- `generic_code_exec`：受限 Python 执行（AST 黑名单校验、禁 import/f-string/危险属性、最小 builtins、子线程 + 30s 超时）——⚠️ 黑名单可经 `__traceback__.tb_frame.f_builtins` 逃逸，故 `code` 步骤已禁止经 HTTP API 模板创建，仅限本地 stdio MCP 通道
- 事件分发：`events/dispatcher.on_court_reply` 将法院回复转为 gate_approved 信号恢复 waiting_event 的 run
- 提供 MCP 工具集（mcp/workflow_tools.py，被 backend/mcp_server 注册）：运行 start/list/detail/approve/cancel/delete、模板 CRUD、以及**从步骤列表一步建模板并启动**（`start_workflow_from_steps`）

## 目录结构

```
workflow/
├── apps.py
├── models/                    # template / run / step
├── api/
│   ├── workflow_api.py        # 实际挂载的路由（运行 + 步骤注册表 + 模板 CRUD）
│   ├── step_registry.py       # 12 个分类约 40 个步骤目录（含 config_schema，供前端编排器渲染表单）
│   └── template_api.py        # 模板 CRUD 平行实现（未挂载，仅单测引用——以 workflow_api.py 为准）
├── temporal/
│   ├── workflows.py           # DynamicWorkflow + INTERNAL_ACTIVITY_MAP / MCP_TOOL_MAP
│   └── activities.py          # 状态回写 + 业务 + 通用 activity（delay/llm/http/code/execute_mcp_tool）
├── mcp/workflow_tools.py      # MCP 工具集（Temporal client 单例）
├── events/dispatcher.py       # 外部事件 → Temporal 信号
├── management/commands/
│   ├── start_temporal_worker.py    # 启动 Worker（优雅关停、每 5 分钟 close_old_connections）
│   └── seed_workflow_templates.py
├── admin/ + schemas/ + fixtures/ + tests/
```

## 数据模型

- `WorkflowTemplate` — 流程模板（steps_schema JSON）
- `WorkflowRun` — 运行实例（绑定 template + case，temporal_workflow_id 唯一，7 种状态）
- `StepExecution` — 步骤执行记录（unique(workflow_run, step_id)，attempts 计数）

## API 端点

前缀 `/api/v1/workflow`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/start` | 按模板 slug + case_id 启动（校验案件访问权并记录 created_by） |
| GET | `/runs`、`/runs/{id}` | 列表 / 详情（详情按案件访问范围校验，含各步骤） |
| POST | `/runs/{id}/approve` | 审批（按 gate 步骤 signal_key 发命名信号，缺省 gate_approved） |
| POST | `/runs/{id}/cancel`、DELETE `/runs/{id}` | 取消 / 删除（先 cancel Temporal） |
| GET | `/step-registry`、`/step-registry/flat` | 步骤注册表 |
| GET/POST | `/templates`、GET/PUT/DELETE `/templates/{id}`、POST `/{id}/duplicate` | 模板 CRUD |

## 运行方式

- Temporal worker 用 `python apiSystem/manage.py start_temporal_worker` 启动（TASK_QUEUE=`fachuan-workflow`，默认地址 localhost:7233）
- Worker 用 `UnsandboxedWorkflowRunner` 规避 Temporal sandbox 拦截 Django 模块导入

## 设计要点

- **Workflow / Activity 分层纪律**：workflow 只做编排（信号、wait_condition、条件求值），所有 ORM/LLM/I/O 放 activity
- **通用信号设计**：DynamicWorkflow 缺省审批信号为 `gate_approved`，gate 步骤可配置 `signal_key` 使用命名信号（须在 WORKFLOW_SIGNAL_HANDLERS 白名单注册，未注册信号会被拒绝而非假成功），靠 `data.step_id` 路由到对应 gate/wait；外部事件（法院回复）也复用
- 步骤注册表既是前端编排器的元数据，也是 AI Agent 建模板前的「可用积木清单」

## 外部集成

Temporal（temporalio）、mcp_server 工具函数（cases/documents/enterprise_data/legal_research/reminders/finance/automation）、plugins.court_automation（可选条件导入立案步骤）、aiohttp、core LLM

## 依赖模块

- `apps.cases`、`apps.documents`、`apps.core`、`apps.organization`、`mcp_server.tools.*`、`plugins.court_automation`（可选）
