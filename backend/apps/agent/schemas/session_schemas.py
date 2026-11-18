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


class MessageIn(Schema):
    """发消息请求体。"""

    message: str


class MessageOut(Schema):
    """会话消息（历史回放）。``metadata`` 含 ``model`` / ``truncated``（中断的回答）等。"""

    message_id: int
    role: str
    content: str
    tool_name: str
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
