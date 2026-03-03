"""Business logic services."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

"""
会话消息服务

负责消息的添加、查询、批量操作和对话摘要管理.
从 LitigationConversationSessionService 中拆分出来.
"""


import logging
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError

from .session_shared import MessageDTO

logger = logging.getLogger("apps.litigation_ai")


class SessionMessageService:
    """会话消息服务 - 管理消息的增删查和对话摘要"""

    def __init__(self) -> None:
        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository
        from apps.litigation_ai.services.wiring import get_conversation_history_service

        self.conversation_history_service = get_conversation_history_service()
        self.session_repo = LitigationSessionRepository()

    @transaction.atomic
    def add_message(
        self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
    ) -> MessageDTO:
        session = self.session_repo.get_session_sync(session_id)
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        msg = self.conversation_history_service.create_message_internal(
            session_id=str(session.session_id),
            user_id=str(session.user_id or ""),
            role=role,
            content=content,
            metadata=metadata or {},
            litigation_session_id=session.id,
            step=(metadata or {}).get("step", ""),
        )
        return self._to_message_dto(msg)

    def get_messages(self, session_id: str, limit: int = 50, offset: int = 0) -> list[MessageDTO]:
        session = self.session_repo.get_session_sync(session_id)
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        items = self.conversation_history_service.list_messages_internal(
            litigation_session_id=session.id,
            limit=limit,
            offset=offset,
            order="asc",
        )
        return [self._to_message_dto(m) for m in items]

    def get_message_count(self, session_id: str) -> int:
        session = self.session_repo.get_session_sync(session_id)
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )
        return self.conversation_history_service.count_messages_internal(litigation_session_id=session.id)

    def get_messages_batch(
        self,
        session_id: str,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[MessageDTO]:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.filter(session_id=session_id).first()
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        items = self.conversation_history_service.list_messages_internal(
            litigation_session_id=session.id,
            limit=limit,
            before_id=before_id,
            order="desc",
        )
        items.reverse()

        return [self._to_message_dto(m) for m in items]

    @transaction.atomic
    def save_conversation_summary(
        self,
        session_id: str,
        summary: str,
    ) -> None:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.filter(session_id=session_id).first()
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        metadata = session.metadata or {}
        metadata["conversation_summary"] = summary
        session.metadata = metadata
        session.save(update_fields=["metadata"])

        logger.info(
            "保存对话摘要",
            extra={
                "session_id": session_id,
                "summary_length": len(summary),
            },
        )

    def get_conversation_summary(self, session_id: str) -> str | None | None:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.filter(session_id=session_id).first()
        if not session:
            return None

        metadata = session.metadata or {}
        return metadata.get("conversation_summary")

    @transaction.atomic
    def add_messages_batch(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> list[MessageDTO]:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.filter(session_id=session_id).first()
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        created_messages = []
        for msg_data in messages:
            msg = self.conversation_history_service.create_message_internal(
                session_id=str(session.session_id),
                user_id=str(session.user_id or ""),
                role=msg_data.get("role", "user"),
                content=msg_data.get("content", ""),
                metadata=msg_data.get("metadata", {}),
                litigation_session_id=session.id,
                step=msg_data.get("metadata", {}).get("step", ""),
            )
            created_messages.append(self._to_message_dto(msg))

        return created_messages

    def _to_message_dto(self, message: Any) -> MessageDTO:
        return MessageDTO(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            metadata=message.metadata,
            created_at=message.created_at,
        )
