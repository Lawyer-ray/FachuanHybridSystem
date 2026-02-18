"""API endpoints."""

from __future__ import annotations

"""
LLM Ninja API

使用 Ninja 框架的 LLM API 接口,集成到主 API 结构中.
"""

import logging
from typing import Any, ClassVar

from ninja import Router
from ninja.schema import Schema

from apps.core.auth import JWTOrSessionAuth
from apps.core.exceptions import PermissionDenied
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .llm_common import achat_with_context as achat_with_context_impl
from .llm_common import get_conversation_history as get_conversation_history_impl
from .llm_common import sync_prompt_templates as sync_prompt_templates_impl

logger = logging.getLogger(__name__)

# 创建 LLM 路由
llm_router = Router(tags=["LLM 服务"], auth=JWTOrSessionAuth())


# ============================================================
# 请求/响应 Schema
# ============================================================


class ChatRequest(Schema):
    """对话请求"""

    message: str
    session_id: str | None = None
    user_id: str | None = None
    system_prompt: str | None = None


class ChatResponse(Schema):
    """对话响应"""

    response: str
    session_id: str


class ConversationMessage(Schema):
    """对话消息"""

    role: str
    content: str
    created_at: str
    metadata: ClassVar[dict[str, Any]] = {}


class ConversationHistoryResponse(Schema):
    """对话历史响应"""

    session_id: str
    messages: list[ConversationMessage]


class SyncTemplatesResponse(Schema):
    """同步模板响应"""

    synced_count: int


# ============================================================
# API 端点
# ============================================================


@llm_router.post("/chat", response=ChatResponse)
@rate_limit_from_settings("LLM", by_user=True)
async def chat_with_context(request: Any, payload: ChatRequest) -> Any:
    """
    带上下文的对话

    支持多轮对话和上下文记忆功能.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    user_id = str(getattr(user, "id", "") or "")

    from apps.core.interfaces import ServiceLocator

    result = await achat_with_context_impl(
        message=payload.message,
        session_id=payload.session_id,
        user_id=user_id,
        system_prompt=payload.system_prompt,
        conversation_service_factory=ServiceLocator.get_conversation_service,
    )

    return ChatResponse(
        response=result["response"],
        session_id=result["session_id"],
    )


@llm_router.post("/chat/stream")
@rate_limit_from_settings("LLM", by_user=True)
async def chat_with_context_stream(request: Any, payload: ChatRequest) -> Any:
    from django.http import StreamingHttpResponse

    from apps.core.interfaces import ServiceLocator
    from apps.core.services.llm_stream_service import build_chat_stream

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    user_id = str(getattr(user, "id", "") or "")

    stream = build_chat_stream(
        message=payload.message,
        session_id=payload.session_id,
        user_id=user_id,
        system_prompt=payload.system_prompt,
        conversation_service_factory=ServiceLocator.get_conversation_service,
        llm_service_factory=ServiceLocator.get_llm_service,
    )

    resp = StreamingHttpResponse(stream, content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    return resp


@llm_router.get("/conversation/{session_id}/history", response=ConversationHistoryResponse)
@rate_limit_from_settings("LLM_HISTORY", by_user=True)
def get_conversation_history(request: Any, session_id: str) -> Any:
    """
    获取对话历史

    返回指定会话的对话记录.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    user_id = str(getattr(user, "id", "") or "")
    is_admin = bool(
        getattr(user, "is_admin", False) or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
    )

    result = get_conversation_history_impl(session_id=session_id, user_id=(None if is_admin else user_id), limit=50)
    messages = [
        ConversationMessage(  # type: ignore[ServiceLocator, call-arg]
            role=m["role"],
            content=m["content"],
            created_at=m["created_at"],
            metadata=m.get("metadata") or {},
        )
        for m in result["messages"]
    ]

    return ConversationHistoryResponse(session_id=session_id, messages=messages)


@llm_router.post("/templates/sync", response=SyncTemplatesResponse)
@rate_limit_from_settings("ADMIN", by_user=True)
def sync_prompt_templates(request: Any) -> Any:
    """
    同步 Prompt 模板

    将代码中的模板同步到数据库.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    is_admin = bool(
        getattr(user, "is_admin", False) or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
    )
    if not is_admin:
        raise PermissionDenied(message="无权限同步模板", code="PERMISSION_DENIED")

    from apps.core.interfaces import ServiceLocator

    result = sync_prompt_templates_impl(prompt_service=ServiceLocator.get_prompt_template_service())
    return SyncTemplatesResponse(synced_count=result["synced_count"])
