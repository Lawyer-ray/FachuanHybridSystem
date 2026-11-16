"""Agent 审批 API —— pi extension 回调闸门、前端决定、审计与待审列表。

端点前缀：``/api/v1/agent``（审批子域）。
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentApproval
from ..schemas import ApprovalDecideIn, PiApprovalIn, PiApprovalOut
from ..services.approval import _waiter_is_alive, classify_risk, decide_approval, get_approval_for_decision
from ..services.approval import list_approvals as list_approval_records
from ..services.approval import list_pending_for_user as list_pending_approvals
from ..services.approval import request_approval
from ._helpers import _current_user, _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 审批"], auth=JWTOrSessionAuth())


def _internal_token_ok(request: Any) -> bool:
    """extension 回调的服务间鉴权。

    - 配置了 ``FACHUAN_INTERNAL_TOKEN``：常数时间比对（防时序侧信道）。
    - 未配置：**仅 DEBUG 开发态放行**并告警；非 DEBUG 一律拒绝（fail-closed）。
      extension 没有用户会话，这个 token 是该端点唯一的鉴权手段。
    """
    expected = os.environ.get("FACHUAN_INTERNAL_TOKEN", "").strip()
    headers = getattr(request, "headers", None)
    provided = headers.get("X-Internal-Token", "") if headers is not None else ""
    if not expected:
        from django.conf import settings as dj_settings

        if getattr(dj_settings, "DEBUG", False):
            logger.warning("FACHUAN_INTERNAL_TOKEN 未配置，审批回调未鉴权（仅限开发环境）")
            return True
        logger.error("生产环境未配置 FACHUAN_INTERNAL_TOKEN，审批回调已拒绝")
        return False
    return hmac.compare_digest(str(provided).encode(), expected.encode())


def _may_decide(user: Any, record: AgentApproval) -> bool:
    """审批归属判定：会话所有者或超级用户；无主会话仅超级用户。"""
    if user is not None and getattr(user, "is_superuser", False):
        return True
    owner_id = getattr(record.session, "user_id", None) if record.session is not None else None
    return user is not None and owner_id is not None and int(owner_id) == int(user.pk)


@router.post("/approval/request", auth=None, response=PiApprovalOut)
async def pi_approval_request(request: Any, payload: PiApprovalIn) -> Any:  # pragma: no cover
    """pi extension 的工具调用审批闸门（同步阻塞等用户回答）。

    鉴权：``X-Internal-Token`` 头（extension 没有用户会话，不走 JWT）。
    """
    if not _internal_token_ok(request):
        return PiApprovalOut(approved=False, reason="鉴权失败")

    level = classify_risk(payload.tool, payload.args)
    if payload.risk_level and payload.risk_level != level.value:
        # extension 与服务端判定不一致：以服务端为准，但记下来便于排查
        # 「为什么一个该拦的操作没弹窗」。
        logger.warning(
            "审批等级不一致 tool=%s extension=%s server=%s",
            payload.tool,
            payload.risk_level,
            level.value,
        )
    approved, approval_id, reason_out = await request_approval(
        tool_name=payload.tool,
        tool_args=payload.args or {},
        user_id=payload.user_id or None,
        session_id=payload.session_id or None,
    )
    return PiApprovalOut(
        approved=approved,
        approval_id=approval_id,
        # 拒绝时带用户填写的理由（无则兜底文案）——模型据此换路径
        reason=reason_out,
        risk_level=level.value,
    )


@router.post("/approval/{approval_id}/decide")
async def submit_approval_decision(  # pragma: no cover
    request: Any,
    approval_id: str,
    payload: ApprovalDecideIn,
) -> dict[str, Any]:
    """前端提交审批决定（仅会话所有者或超级用户可决定）。"""
    user = _current_user(request)
    record = await get_approval_for_decision(approval_id)

    if record is not None and not _may_decide(user, record):
        return {"success": False, "approved": payload.approved, "error": "无权审批该请求"}

    ok = await decide_approval(approval_id, payload.approved, user_id=_user_id(request), reason=payload.reason)
    return {"success": ok, "approved": payload.approved}


@router.get("/approvals/pending", response=list[dict[str, Any]])
async def list_pending_approvals_endpoint(request: Any) -> list[dict[str, Any]]:  # pragma: no cover
    """当前用户**仍待处理**的审批（离线审批入口）。

    任务式后台运行没有 SSE 连接，高危工具会挂起等决定。用户下次打开
    对话页时调这个接口，把待审批卡片摆出来——而不是让那次运行默默超时。
    """
    records = await list_pending_approvals(user_id=_user_id(request))
    return [
        {
            "approval_id": str(a.approval_id),
            "session_id": str(a.session.session_id) if a.session is not None else "",
            "tool_name": a.tool_name,
            "tool_args": a.tool_args or {},
            "risk_level": a.risk_level,
            "created_at": a.created_at.isoformat(),
            # P2-4：等待进程已死（心跳键过期）——前端可提示「该审批可能已失效」
            "waiter_dead": not _waiter_is_alive(str(a.approval_id)),
        }
        for a in records
    ]


@router.get("/approvals", response=list[dict[str, Any]])
async def list_approvals(request: Any, limit: int = 50) -> list[dict[str, Any]]:  # pragma: no cover
    """列出审批记录（审计用；非超级用户仅见自己会话的记录）。"""
    records = await list_approval_records(user=_current_user(request), limit=limit)
    return [
        {
            "approval_id": str(a.approval_id),
            "tool_name": a.tool_name,
            "risk_level": a.risk_level,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in records
    ]
