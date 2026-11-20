"""会话 / 消息 / 统计 / 压缩的请求响应契约。"""

from __future__ import annotations

from typing import Any

from ninja import Schema


class SessionIn(Schema):
    """创建会话请求体。

    不接受模型参数：模型由服务端按 LLMProvider 配置解析，客户端传了也不会生效，
    所以不在契约里留这个诱饵（``SessionOut.llm_model`` 回报的是实际使用的模型）。
    """

    title: str = ""
    #: 来源入口：chat（对话页）/ case（案件内）/ contract（合同内）/ task（任务式）
    origin: str = "chat"
    case_id: int | None = None
    contract_id: int | None = None
    #: 本会话用哪个 agent 后端（默认 `pi`）。
    #:
    #: **刻意留在契约里**（与模型参数相反：模型由服务端解析、客户端传了不生效）：
    #: agent 后端是用户的选择而非部署配置，同一律师可能在不同会话里分别问
    #: pi 和其他后端做对比，所以必须是客户端可指定的。
    #: 未注册的 kind 在创建时拒绝（而不是静默回退到 pi），否则用户以为换了后端
    #: 实际没换——这种「假切换」比报错更难发现。
    agent_kind: str = "pi"


class SessionOut(Schema):
    """会话输出。``llm_model`` 为最近一轮对话实际使用的模型（未对话过为空）。"""

    session_id: str
    title: str
    status: str
    llm_model: str
    #: 本会话使用的 agent 后端。历史会话回填为 `pi`。
    agent_kind: str = "pi"
    origin: str
    case_id: int | None = None
    contract_id: int | None = None
    #: 任务式会话的进度（queued/running/succeeded/failed/cancelled）；
    #: 非 task 会话为空串。
    task_state: str = ""
    task_id: str = ""
    task_error: str = ""
    task_finished_at: str = ""
    #: 业务范围名（案件名 / 委托人客户名），由列表接口批量注水，
    #: 供前端按业务分组展示；通用与任务会话为空串。
    scope_name: str = ""
    created_at: str
    updated_at: str


class SessionRenameIn(Schema):
    """重命名会话请求体。"""

    title: str


class AgentSpecIn(Schema):
    """本轮一个参与方：哪个后端 + 用哪个模型。"""

    #: 后端 kind（``SessionIn.agent_kind`` 的合法取值）。
    kind: str
    #: 该栏用的模型；空/``None`` = 用平台默认（与引入本字段前的行为一致）。
    model: str | None = None


class MessageIn(Schema):
    """发消息请求体。"""

    message: str
    #: 本轮要同时问哪几个 agent，可逐栏指定模型。
    #:
    #: 空 / ``None`` = 用会话自己选的后端单跑。长度 1 = 单跑那一个。
    #: 长度 ≥2 = 多答，各栏并排显示。
    #:
    #: **两种形态混用**：新前端发 ``[{"kind":"pi","model":"kimi-2.6"},
    #: {"kind":"dsh"}]``，老前端发 ``["pi","dsh"]``。两种都必须能过校验——
    #: 选模型的收益不该以「旧前端全挂（422）」为代价。归一化在
    #: ``services/chat/multi.normalize_agents``（字符串/字典/``AgentSpec`` 都认）。
    #:
    #: **为什么是显式清单而不是「让后端自己挑」**：加第 4、5 个 agent 时编排层
    #: 不该有任何改动。让调用方把本轮参与方说清楚，注册表里多一个 kind 不需要
    #: 动 ``multi.py`` 一个字。
    #:
    #: 上限见 ``services/chat/multi.MAX_ANSWERS``（超了 API 层返回 400，不静默
    #: 截断——静默截断会让用户以为选中的都跑了）。
    agents: list[AgentSpecIn | str] | None = None
    #: 旧前端的「双答」开关，等价于 ``agents=[会话默认, 次选]``。
    #:
    #: **保留是为了兼容**：老客户端只会发 ``dual: true``。两处都给时 ``agents``
    #: 优先（显式 > 隐式）。新前端请直接用 ``agents``。
    #:
    #: **默认 False**：成本随栏数线性增长，不能默认开。这不是会话级属性——律师
    #: 可以逐轮决定要不要对比，所以放在消息请求体而不是 ``SessionIn`` 里。
    dual: bool = False


class MessageOut(Schema):
    """会话消息（历史回放）。``metadata`` 含 ``model`` / ``truncated``（中断的回答）等。"""

    message_id: int
    role: str
    content: str
    tool_name: str
    #: 这条消息来自哪个 agent。空串 = 旧数据 / 未标注（引入字段前的记录），
    #: 前端渲染时当 ``pi`` 处理。
    agent_kind: str = ""
    #: 律师反馈：``up`` / ``down``；空串 = 未评分。
    #:
    #: 撤销（``POST /agent/messages/{id}/rating`` 的 ``none``）是**删键**，
    #: 回放时同样读成空串——所以空串不区分「从没评过」与「评过又撤销」，
    #: 这两种状态前端要画的东西一样（两个按钮都不高亮）。
    #: 数据源是 ``metadata["rating"]``，见 ``agent/services/message_rating``。
    rating: str = ""
    created_at: str
    metadata: dict[str, Any] = {}


class SessionStatsOut(Schema):
    """会话累计用量与上下文水位（最新一轮 AgentRun 的快照）。

    水位 nullable：旧轮数据 / pi 未上报时是 None，前端隐藏水位显示，
    不把「不知道」伪装成「上下文是空的」。
    """

    output_tokens: int
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    context_used_tokens: int | None = None
    context_total_tokens: int | None = None
    context_percent: float | None = None


class CompactOut(Schema):
    """手动压缩回执。``compacted=False`` 表示无历史可压（幂等成功，不报错）。"""

    compacted: bool
    context_used_tokens: int | None = None
    context_total_tokens: int | None = None
