"""Agent API —— 会话管理与对话入口。

端点前缀：``/api/v1/agent``

- 会话：创建 / 列表 / 详情 / 删除
- 对话：SSE 流式（事件契约见 services/chat_service.py）
- 审批：extension 回调入口 + 前端决定入口
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from django.http import StreamingHttpResponse
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentApproval, AgentMessage, AgentSession
from ..services.approval import decide_approval, request_approval
from ..services.chat_service import stream_chat

logger = logging.getLogger(__name__)

router = Router(tags=["Agent"], auth=JWTOrSessionAuth())


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SessionIn(Schema):
    """创建会话请求体。"""

    title: str = ""
    llm_model: str = ""


class SessionOut(Schema):
    """会话输出。"""

    session_id: str
    title: str
    status: str
    llm_model: str
    created_at: str
    updated_at: str


class MessageIn(Schema):
    """发消息请求体。"""

    message: str
    llm_model: str = ""


class ApprovalDecideIn(Schema):
    """前端审批决定。"""

    approved: bool


class PiApprovalIn(Schema):
    """pi extension 发来的审批请求。"""

    tool: str
    args: dict[str, Any] | None = None
    user_id: int = 0
    session_id: str = ""


class PiApprovalOut(Schema):
    """审批结果（只有 approved=true 放行）。"""

    approved: bool
    approval_id: str = ""
    reason: str = ""


def _user_id(request: Any) -> int | None:
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return int(user.pk)
    return None


def _to_out(session: AgentSession) -> SessionOut:
    return SessionOut(
        session_id=str(session.session_id),
        title=session.title,
        status=session.status,
        llm_model=session.llm_model,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


# ─── 会话 ───────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
async def create_session(request: Any, payload: SessionIn) -> SessionOut:  # pragma: no cover
    """新建会话。"""
    session = await AgentSession.objects.acreate(
        title=payload.title,
        llm_model=payload.llm_model,
        user_id=_user_id(request),
    )
    return _to_out(session)


@router.get("/sessions", response=list[SessionOut])
async def list_sessions(request: Any, limit: int = 50) -> list[SessionOut]:  # pragma: no cover
    """列出当前用户的会话。"""
    user_id = _user_id(request)
    queryset = AgentSession.objects.all()
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    sessions = [s async for s in queryset[: max(1, min(limit, 200))]]
    return [_to_out(s) for s in sessions]


@router.delete("/sessions/{session_id}")
async def delete_session(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """删除会话（级联删除消息与审批）。"""
    user_id = _user_id(request)
    queryset = AgentSession.objects.filter(session_id=session_id)
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    deleted, _ = await queryset.adelete()
    return {"deleted": deleted}


# ─── 对话 ───────────────────────────────────────────────────────────────────


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@router.post("/sessions/{session_id}/messages")
async def send_message(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: MessageIn,
) -> StreamingHttpResponse:
    """发消息并流式返回（SSE）。"""
    user_id = _user_id(request)
    session = await AgentSession.objects.filter(session_id=session_id).afirst()
    if session is None:
        return StreamingHttpResponse(
            _sse({"type": "error", "message": "会话不存在"}),
            content_type="text/event-stream",
        )

    async def generator() -> AsyncIterator[bytes]:
        async for event in stream_chat(
            session=session,
            user_message=payload.message,
            user_id=user_id,
        ):
            yield _sse(event)

    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ─── 审批 ───────────────────────────────────────────────────────────────────


def _internal_token_ok(request: Any) -> bool:
    """extension 回调的服务间鉴权。

    未配置 ``FACHUAN_INTERNAL_TOKEN`` 时（开发环境）放行，但记录告警；
    生产必须配置。
    """
    expected = os.environ.get("FACHUAN_INTERNAL_TOKEN", "").strip()
    if not expected:
        logger.warning("FACHUAN_INTERNAL_TOKEN 未配置，审批回调未鉴权（仅限开发环境）")
        return True
    headers = getattr(request, "headers", None)
    provided = headers.get("X-Internal-Token", "") if headers is not None else ""
    return str(provided) == expected


@router.post("/approval/request", auth=None, response=PiApprovalOut)
async def pi_approval_request(request: Any, payload: PiApprovalIn) -> Any:  # pragma: no cover
    """pi extension 的工具调用审批闸门（同步阻塞等用户回答）。

    鉴权：``X-Internal-Token`` 头（extension 没有用户会话，不走 JWT）。
    """
    if not _internal_token_ok(request):
        return PiApprovalOut(approved=False, reason="鉴权失败")

    approved, approval_id = await request_approval(
        tool_name=payload.tool,
        tool_args=payload.args or {},
        user_id=payload.user_id or None,
        session_id=payload.session_id or None,
    )
    return PiApprovalOut(
        approved=approved,
        approval_id=approval_id,
        reason="用户同意" if approved else "用户拒绝或超时",
    )


@router.post("/approval/{approval_id}/decide")
async def submit_approval_decision(  # pragma: no cover
    request: Any,
    approval_id: str,
    payload: ApprovalDecideIn,
) -> dict[str, Any]:
    """前端提交审批决定。"""
    ok = await decide_approval(approval_id, payload.approved, user_id=_user_id(request))
    return {"success": ok, "approved": payload.approved}


@router.get("/approvals", response=list[dict[str, Any]])
async def list_approvals(request: Any, limit: int = 50) -> list[dict[str, Any]]:  # pragma: no cover
    """列出审批记录（审计用）。"""
    records = [a async for a in AgentApproval.objects.all()[: max(1, min(limit, 200))]]
    return [
        {
            "approval_id": str(a.approval_id),
            "tool_name": a.tool_name,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in records
    ]
