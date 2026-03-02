"""API endpoints."""

from __future__ import annotations

"""
LLM API 共享实现
"""

from collections.abc import Callable
from typing import Any, cast


def chat_with_context(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    system_prompt: str | None = None,
    conversation_service_factory: Callable[..., Any] | None = None,
) -> dict[str, str]:
    conversation_service = conversation_service_factory(session_id=session_id, user_id=user_id)  # type: ignore[misc]
    response = conversation_service.chat_with_context(
        user_message=message,
        system_prompt=system_prompt,
    )
    return {"response": response, "session_id": conversation_service.session_id}


async def achat_with_context(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    system_prompt: str | None = None,
    conversation_service_factory: Callable[..., Any] | None = None,
) -> dict[str, str]:
    from asgiref.sync import sync_to_async

    def _run() -> Any:
        conversation_service = conversation_service_factory(session_id=session_id, user_id=user_id)  # type: ignore[misc]
        response = conversation_service.chat_with_context(
            user_message=message,
            system_prompt=system_prompt,
        )
        return {"response": response, "session_id": conversation_service.session_id}

    return cast(dict[str, str], await sync_to_async(_run, thread_sensitive=True)())


def _get_conversation_history_service() -> Any:
    from apps.core.services.conversation_history_service import ConversationHistoryService

    return ConversationHistoryService()


def get_conversation_history(session_id: str, user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    service = _get_conversation_history_service()
    messages = service.get_conversation_history_messages(session_id=session_id, user_id=user_id, limit=limit)
    return {"session_id": session_id, "messages": messages}

