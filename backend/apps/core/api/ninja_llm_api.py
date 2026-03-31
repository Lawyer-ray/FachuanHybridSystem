"""API endpoints."""

"""
LLM Ninja API

使用 Ninja 框架的 LLM API 接口,集成到主 API 结构中.
"""

import logging
from typing import Any, ClassVar

from django.db import transaction
from ninja import Router
from ninja.schema import Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.core.exceptions import PermissionDenied
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .llm_common import achat_with_context as achat_with_context_impl
from .llm_common import get_conversation_history as get_conversation_history_impl

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


class PromptTemplateSyncResponse(Schema):
    """Prompt 模板同步响应"""

    synced_count: int


def sync_prompt_templates_impl(*, overwrite: bool = True) -> dict[str, int]:
    """
    将代码内置 Prompt 模板同步到数据库。

    该函数保留模块级命名，兼容旧测试对 `sync_prompt_templates_impl` 的 monkeypatch。
    """
    from apps.core.llm.prompts import PromptManager
    from apps.core.models import PromptTemplate

    templates = list(PromptManager._templates.values())
    synced_count = 0
    with transaction.atomic():
        for item in templates:
            defaults = {
                "title": (item.description or item.name)[:200],
                "template": item.template,
                "description": item.description,
                "variables": item.variables,
                "category": (item.name.split("_", maxsplit=1)[0] or "general"),
                "is_active": True,
                "version": "1.0",
            }
            if overwrite:
                PromptTemplate.objects.update_or_create(name=item.name, defaults=defaults)
                synced_count += 1
                continue
            _, created = PromptTemplate.objects.get_or_create(name=item.name, defaults=defaults)
            if created:
                synced_count += 1
    return {"synced_count": synced_count}


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
        ConversationMessage(  # type: ignore[call-arg]
            role=m["role"],
            content=m["content"],
            created_at=m["created_at"],
            metadata=m.get("metadata") or {},
        )
        for m in result["messages"]
    ]

    return ConversationHistoryResponse(session_id=session_id, messages=messages)


@llm_router.post("/templates/sync", response=PromptTemplateSyncResponse)
@rate_limit_from_settings("LLM", by_user=True)
def sync_prompt_templates(request: Any) -> Any:
    """
    同步代码内置 Prompt 模板到数据库（仅管理员）。
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    is_admin = bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
    if not is_admin:
        raise PermissionDenied(message="需要管理员权限", code="PERMISSION_DENIED")

    result = sync_prompt_templates_impl(overwrite=True)
    return PromptTemplateSyncResponse(synced_count=int(result.get("synced_count", 0)))
