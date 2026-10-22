"""Agent API —— 会话管理与对话入口。

端点前缀：``/api/v1/agent``

- 会话：创建 / 列表 / 详情 / 消息历史 / 删除
- 对话：SSE 流式（事件契约见 services/chat_service.py）
- 审批：extension 回调入口 + 前端决定入口
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from django.http import StreamingHttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentApproval, AgentMessage, AgentSession
from ..services.approval import decide_approval, get_approval_for_decision
from ..services.approval import list_approvals as list_approval_records
from ..services.approval import request_approval
from ..services.chat_service import stream_chat
from ..services.session_service import create_session as create_session_record
from ..services.session_service import delete_session as delete_session_record
from ..services.session_service import get_session as get_session_record
from ..services.session_service import list_messages as list_message_records
from ..services.session_service import list_sessions as list_session_records
from ..services.session_service import rename_session as rename_session_record

logger = logging.getLogger(__name__)

router = Router(tags=["Agent"], auth=JWTOrSessionAuth())


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SessionIn(Schema):
    """创建会话请求体。

    不接受模型参数：模型由服务端按 LLMProvider 配置解析，客户端传了也不会生效，
    所以不在契约里留这个诱饵（``SessionOut.llm_model`` 回报的是实际使用的模型）。
    """

    title: str = ""


class SessionOut(Schema):
    """会话输出。``llm_model`` 为最近一轮对话实际使用的模型（未对话过为空）。"""

    session_id: str
    title: str
    status: str
    llm_model: str
    created_at: str
    updated_at: str


class MessageIn(Schema):
    """发消息请求体。"""

    message: str


class SessionRenameIn(Schema):
    """重命名会话请求体。"""

    title: str


class MessageOut(Schema):
    """会话消息（历史回放）。``metadata`` 含 ``model`` / ``truncated``（中断的回答）等。"""

    message_id: int
    role: str
    content: str
    tool_name: str
    created_at: str
    metadata: dict[str, Any] = {}


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


def _current_user(request: Any) -> Any:
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _user_id(request: Any) -> int | None:
    user = _current_user(request)
    return int(user.pk) if user is not None else None


def _to_out(session: AgentSession) -> SessionOut:
    return SessionOut(
        session_id=str(session.session_id),
        title=session.title,
        status=session.status,
        llm_model=session.llm_model,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


def _message_out(message: AgentMessage) -> MessageOut:
    return MessageOut(
        message_id=message.pk,
        role=message.role,
        content=message.content,
        tool_name=message.tool_name,
        created_at=message.created_at.isoformat(),
        metadata=message.metadata or {},
    )


# ─── 会话 ───────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
async def create_session(request: Any, payload: SessionIn) -> SessionOut:  # pragma: no cover
    """新建会话。"""
    session = await create_session_record(
        title=payload.title,
        user_id=_user_id(request),
    )
    return _to_out(session)


@router.get("/sessions", response=list[SessionOut])
async def list_sessions(request: Any, limit: int = 50) -> list[SessionOut]:  # pragma: no cover
    """列出当前用户的会话。"""
    sessions = await list_session_records(user_id=_user_id(request), limit=limit)
    return [_to_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response=SessionOut)
async def get_session_detail(request: Any, session_id: str) -> SessionOut:  # pragma: no cover
    """会话详情（不归属当前用户时同样 404，不泄露存在性）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


@router.get("/sessions/{session_id}/messages", response=list[MessageOut])
async def list_messages(request: Any, session_id: str, limit: int = 200) -> list[MessageOut]:  # pragma: no cover
    """会话消息历史（旧→新），前端重开会话时据此回放转录。"""
    messages = await list_message_records(session_id=session_id, user_id=_user_id(request), limit=limit)
    if messages is None:
        raise HttpError(404, "会话不存在")
    return [_message_out(m) for m in messages]


@router.delete("/sessions/{session_id}")
async def delete_session(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """删除会话（级联删除消息与审批）。"""
    deleted = await delete_session_record(session_id=session_id, user_id=_user_id(request))
    return {"deleted": deleted}


@router.patch("/sessions/{session_id}", response=SessionOut)
async def update_session_title(
    request: Any, session_id: str, payload: SessionRenameIn
) -> SessionOut:  # pragma: no cover
    """重命名会话（侧边栏会话列表的改名入口）。"""
    if not payload.title.strip():
        raise HttpError(400, "标题不能为空")
    session = await rename_session_record(
        session_id=session_id,
        user_id=_user_id(request),
        title=payload.title,
    )
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


# ─── 对话 ───────────────────────────────────────────────────────────────────


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@router.post("/sessions/{session_id}/messages")
async def send_message(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: MessageIn,
) -> Any:
    """发消息并流式返回（SSE）。"""
    user_id = _user_id(request)
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        return StreamingHttpResponse(
            # 必须传可迭代对象：直接传 bytes 会被逐字节迭代成 int，
            # 前端收到的是一串十进制数字
            iter([_sse({"type": "error", "message": "会话不存在"})]),
            content_type="text/event-stream",
        )

    async def generator() -> AsyncIterator[bytes]:
        # 会话对象在流式阶段重新取：ORM 实例带着数据库连接状态，
        # 跨到 StreamingHttpResponse 的异步迭代阶段可能已失效。
        current = await get_session_record(session_id=session_id, user_id=user_id)
        if current is None:
            yield _sse({"type": "error", "message": "会话不存在"})
            return
        try:
            async for event in stream_chat(
                session=current,
                user_message=payload.message,
                user_id=user_id,
            ):
                yield _sse(event)
        except Exception:
            logger.exception("SSE 生成器异常")
            yield _sse({"type": "error", "message": "流处理异常，请稍后重试"})

    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ─── 审批 ───────────────────────────────────────────────────────────────────


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
    """前端提交审批决定（仅会话所有者或超级用户可决定）。"""
    user = _current_user(request)
    record = await get_approval_for_decision(approval_id)

    if record is not None and not _may_decide(user, record):
        return {"success": False, "approved": payload.approved, "error": "无权审批该请求"}

    ok = await decide_approval(approval_id, payload.approved, user_id=_user_id(request))
    return {"success": ok, "approved": payload.approved}


def _may_decide(user: Any, record: AgentApproval) -> bool:
    """审批归属判定：会话所有者或超级用户；无主会话仅超级用户。"""
    if user is not None and getattr(user, "is_superuser", False):
        return True
    owner_id = getattr(record.session, "user_id", None) if record.session is not None else None
    return user is not None and owner_id is not None and int(owner_id) == int(user.pk)


@router.get("/approvals", response=list[dict[str, Any]])
async def list_approvals(request: Any, limit: int = 50) -> list[dict[str, Any]]:  # pragma: no cover
    """列出审批记录（审计用；非超级用户仅见自己会话的记录）。"""
    records = await list_approval_records(user=_current_user(request), limit=limit)
    return [
        {
            "approval_id": str(a.approval_id),
            "tool_name": a.tool_name,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in records
    ]
