"""Business logic services."""

from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async


class FlowMessenger:
    def __init__(self, conversation_service: Any) -> None:
        self.conversation_service = conversation_service

    async def persist_message(
        self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        await sync_to_async(self.conversation_service.add_message, thread_sensitive=True)(
            session_id=session_id, role=role, content=content, metadata=metadata or {}
        )

    async def send(
        self,
        send_callback: Callable[..., Any],
        payload: dict[str, Any],
        persist: bool,
        session_id: str,
        role: str,
    ) -> None:
        await send_callback(payload)
        if persist:
            await self.persist_message(
                session_id=session_id,
                role=role,
                content=payload.get("content", ""),
                metadata=payload.get("metadata", {}),
            )
