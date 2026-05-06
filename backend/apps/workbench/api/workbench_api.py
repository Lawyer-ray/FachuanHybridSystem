"""工作台 API 路由"""

from __future__ import annotations

import json
from typing import Any

from django.http import Http404, StreamingHttpResponse
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..models import WorkbenchMessage, WorkbenchSession
from ..schemas import MessageIn, MessageOut, SessionCreateIn, SessionOut, SessionUpdateIn
from ..services import WorkbenchChatService

router = Router(auth=JWTOrSessionAuth())

# 全局服务实例（用于审批回调共享状态）
_chat_service = WorkbenchChatService()


def _get_user_session(user: Any, session_id: int) -> WorkbenchSession:
    """获取用户的会话，不存在或无权限时抛 404"""
    try:
        return WorkbenchSession.objects.get(id=session_id, user=user)
    except WorkbenchSession.DoesNotExist:
        raise Http404("会话不存在")


# ─── 会话 API ────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
def create_session(request: Any, payload: SessionCreateIn) -> WorkbenchSession:
    """创建工作台会话"""
    user = request.user
    session = WorkbenchSession.objects.create(
        user=user if user.is_authenticated else None,
        title=payload.title,
        llm_model=payload.llm_model,
    )
    return session


@router.get("/sessions")
def list_sessions(request: Any, page: int = 1) -> dict[str, Any]:
    """获取当前用户的工作台会话列表"""
    user = request.user
    if user.is_authenticated:
        qs = WorkbenchSession.objects.filter(user=user).order_by("-updated_at")
    else:
        qs = WorkbenchSession.objects.none()

    page_size = 20
    offset = (page - 1) * page_size
    total = qs.count()
    items = list(qs[offset : offset + page_size])

    return {
        "items": [SessionOut.model_validate(item).model_dump() for item in items],
        "count": total,
    }


@router.get("/sessions/{session_id}", response=SessionOut)
def get_session(request: Any, session_id: int) -> WorkbenchSession:
    """获取会话详情"""
    return _get_user_session(request.user, session_id)


@router.patch("/sessions/{session_id}", response=SessionOut)
def update_session(request: Any, session_id: int, payload: SessionUpdateIn) -> WorkbenchSession:
    """更新会话"""
    session = _get_user_session(request.user, session_id)
    if payload.title is not None:
        session.title = payload.title
    if payload.llm_model is not None:
        session.llm_model = payload.llm_model
    if payload.status is not None:
        session.status = payload.status
    session.save()
    return session


@router.delete("/sessions/{session_id}")
def delete_session(request: Any, session_id: int) -> dict[str, str]:
    """删除会话"""
    session = _get_user_session(request.user, session_id)
    session.delete()
    return {"message": "已删除"}


# ─── 消息 API ────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/messages")
def list_messages(request: Any, session_id: int, page: int = 1) -> dict[str, Any]:
    """获取会话的消息列表"""
    _get_user_session(request.user, session_id)
    qs = WorkbenchMessage.objects.filter(session_id=session_id).order_by("created_at")
    page_size = 50
    offset = (page - 1) * page_size
    total = qs.count()
    items = list(qs[offset : offset + page_size])

    return {
        "items": [MessageOut.model_validate(item).model_dump() for item in items],
        "count": total,
    }


@router.delete("/sessions/{session_id}/messages/from/{message_id}")
def truncate_messages(request: Any, session_id: int, message_id: int) -> dict[str, str]:
    """删除指定消息及其之后的所有消息（用于编辑重发）"""
    _get_user_session(request.user, session_id)
    try:
        msg = WorkbenchMessage.objects.get(id=message_id, session_id=session_id)
    except WorkbenchMessage.DoesNotExist:
        raise Http404("消息不存在")
    WorkbenchMessage.objects.filter(
        session_id=session_id,
        created_at__gte=msg.created_at,
    ).delete()
    return {"message": "已截断"}


class FeedbackIn(Schema):
    """消息反馈请求体"""

    rating: str  # 'good' | 'bad'
    comment: str = ""


@router.patch("/messages/{message_id}/feedback")
def submit_feedback(request: Any, message_id: int, payload: FeedbackIn) -> dict[str, Any]:
    """提交消息反馈（好评/差评）"""
    if payload.rating not in ("good", "bad"):
        return {"success": False, "message": "rating 必须是 good 或 bad"}

    try:
        msg = WorkbenchMessage.objects.get(id=message_id)
    except WorkbenchMessage.DoesNotExist:
        raise Http404("消息不存在")

    # 校验消息属于当前用户的会话
    _get_user_session(request.user, msg.session_id)

    meta = dict(msg.metadata or {})
    meta["feedback"] = {"rating": payload.rating, "comment": payload.comment}
    msg.metadata = meta
    msg.save(update_fields=["metadata"])

    return {"success": True, "message": "反馈已提交"}


# ─── 对话 API（SSE 流式） ────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/messages/stream")
async def stream_chat(request: Any, session_id: int, payload: MessageIn) -> StreamingHttpResponse:
    """SSE 流式对话 - 发送消息并获取 AI 流式响应"""
    try:
        await WorkbenchSession.objects.aget(id=session_id, user=request.user)
    except WorkbenchSession.DoesNotExist:
        raise Http404("会话不存在")

    async def event_generator() -> Any:
        async for event in _chat_service.stream_chat(
            session_id=session_id,
            user_message=payload.content,
            llm_model=payload.llm_model or "",
            agent_type=payload.agent_type or "",
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── 审批 API（Phase 2） ─────────────────────────────────────────────────────


class ApprovalIn(Schema):
    """审批请求体"""

    approval_id: str
    approved: bool


@router.post("/approval")
def respond_approval(request: Any, payload: ApprovalIn) -> dict[str, Any]:
    """响应审批请求（Phase 2: Human-in-the-Loop）"""
    user_id = request.user.id if request.user.is_authenticated else None
    success = _chat_service.resolve_approval(payload.approval_id, payload.approved, user_id=user_id)
    return {
        "success": success,
        "message": "审批已处理" if success else "审批 ID 不存在或已过期",
    }


# ─── 模型列表 API ────────────────────────────────────────────────────────────


@router.get("/models")
def list_models(request: Any) -> dict[str, Any]:
    """获取可用的 LLM 模型列表（默认模型取列表第一个）"""
    from apps.core.llm.model_list_service import ModelListService

    service = ModelListService()
    result = service.get_result()

    default_model = result.models[0]["id"] if result.models else ""

    return {
        "models": result.models,
        "default_model": default_model,
        "is_fallback": result.is_fallback,
        "error_message": result.error_message,
    }
