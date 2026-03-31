"""Business logic services."""

from typing import Any

from django.db.models import Count

from apps.core.dto import ConversationHistoryDTO
from apps.core.models import ConversationHistory
from apps.core.repositories import ConversationHistoryRepository


class ConversationHistoryService:
    def __init__(self, *, repository: ConversationHistoryRepository | None = None) -> None:
        self._repository = repository or ConversationHistoryRepository()

    def create_message_internal(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any],
        litigation_session_id: int | None = None,
        step: str = "",
    ) -> ConversationHistoryDTO:
        record = self._repository.create(
            session_id=str(session_id),
            user_id=str(user_id or ""),
            role=role,
            content=content,
            metadata=metadata or {},
            litigation_session_id=litigation_session_id,
            step=step or "",
        )
        return self._to_dto(record)

    def list_messages_internal(
        self,
        *,
        session_id: str | None = None,
        litigation_session_id: int | None = None,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
        before_id: int | None = None,
        order: str = "asc",
    ) -> list[ConversationHistoryDTO]:
        if not session_id and not litigation_session_id:
            return []

        qs = self._repository.get_all()
        if session_id:
            qs = qs.filter(session_id=str(session_id))
        if litigation_session_id:
            qs = qs.filter(litigation_session_id=litigation_session_id)
        if role:
            qs = qs.filter(role=role)
        if before_id:
            qs = qs.filter(id__lt=before_id)

        if (order or "").lower() == "desc":
            qs = qs.order_by("-created_at")
        else:
            qs = qs.order_by("created_at")

        records = list(qs[offset : offset + limit])
        return [self._to_dto(r) for r in records]

    def count_messages_internal(
        self,
        *,
        session_id: str | None = None,
        litigation_session_id: int | None = None,
    ) -> int:
        if not session_id and not litigation_session_id:
            return 0

        qs = self._repository.get_all()
        if session_id:
            qs = qs.filter(session_id=str(session_id))
        if litigation_session_id:
            qs = qs.filter(litigation_session_id=litigation_session_id)
        return qs.count()

    def count_messages_by_litigation_session_ids_internal(self, *, litigation_session_ids: list[int]) -> dict[int, int]:
        if not litigation_session_ids:
            return {}

        rows = (
            self._repository.get_by_litigation_session_ids(litigation_session_ids)
            .values("litigation_session_id")
            .annotate(cnt=Count("id"))
        )
        return {row["litigation_session_id"]: row["cnt"] for row in rows}

    def _to_dto(self, record: ConversationHistory) -> ConversationHistoryDTO:
        return ConversationHistoryDTO(
            id=record.pk,
            session_id=record.session_id,
            user_id=record.user_id,
            role=record.role,
            content=record.content,
            metadata=record.metadata,
            created_at=record.created_at,
            litigation_session_id=record.litigation_session_id,
            step=record.step or "",
        )

    def get_conversation_history_messages(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取对话历史消息列表(用于 API 层)

        Args:
            session_id: 会话 ID
            user_id: 用户 ID(可选)
            limit: 返回数量限制

        Returns:
            消息列表,按时间正序排列
        """
        qs = self._repository.get_by_session_id(session_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        history = list(qs.order_by("-created_at")[:limit])

        messages: list[dict[str, Any]] = []
        for record in reversed(history):
            messages.append(
                {
                    "role": record.role,
                    "content": record.content,
                    "created_at": record.created_at.isoformat(),
                    "metadata": record.metadata,
                }
            )
        return messages
