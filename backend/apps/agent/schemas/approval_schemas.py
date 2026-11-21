"""审批的请求响应契约（前端决定 + pi extension 回调）。"""

from __future__ import annotations

from typing import Any

from ninja import Schema


class ApprovalDecideIn(Schema):
    """前端审批决定。"""

    approved: bool
    #: 拒绝理由（可空）：回传给模型，引导换更安全的路径而不是干巴巴的「用户拒绝」
    reason: str = ""


class PiApprovalIn(Schema):
    """pi extension 发来的审批请求。

    ``risk_level`` 由 extension 预判后一并送来（仅作参考与日志），
    服务端以 ``classify_risk`` 的判定为准——extension 可以被绕过，
    不能让客户端决定自己要不要审批。
    """

    tool: str
    args: dict[str, Any] | None = None
    user_id: int = 0
    session_id: str = ""
    risk_level: str = ""
    #: 运行标识 ``{session_id}:{agent_kind}:{turn}``。多栏并答时审批卡靠它归到
    #: 正确那一栏；缺失（旧 extension）不报错，只丢归因。
    run_id: str = ""
    #: 工具调用标识（同轮内区分两次同名调用）。
    tool_call_id: str = ""
    #: 发起方给的理由，落 ``AgentApproval.reason``（与驳回理由分列，互不覆盖）。
    reason: str = ""


class PiApprovalOut(Schema):
    """审批结果（只有 approved=true 放行）。"""

    approved: bool
    approval_id: str = ""
    reason: str = ""
    risk_level: str = ""
