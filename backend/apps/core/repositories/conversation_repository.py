"""
ConversationHistory Repository

封装 ConversationHistory 模型的数据访问操作
"""

from typing import Any

from django.db.models import QuerySet

from apps.core.models.conversation import ConversationHistory


class ConversationHistoryRepository:
    """对话历史数据访问层"""

    def create(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any],
        litigation_session_id: int | None = None,
        step: str = "",
    ) -> ConversationHistory:
        return ConversationHistory.objects.create(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata,
            litigation_session_id=litigation_session_id,
            step=step,
        )

    def get_by_session_id(self, session_id: str, user_id: str | None = None) -> QuerySet[ConversationHistory]:
        qs = ConversationHistory.objects.filter(session_id=session_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def get_by_litigation_session_ids(self, litigation_session_ids: list[int]) -> QuerySet[ConversationHistory]:
        return ConversationHistory.objects.filter(litigation_session_id__in=litigation_session_ids)

    def get_all(self) -> QuerySet[ConversationHistory]:
        return ConversationHistory.objects.all()

    def delete_by_session_id(self, session_id: str, user_id: str | None = None) -> tuple[int, dict[str, int]]:
        qs = ConversationHistory.objects.filter(session_id=session_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs.delete()

    async def acreate(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any],
        litigation_session_id: int | None = None,
        step: str = "",
    ) -> ConversationHistory:
        return await ConversationHistory.objects.acreate(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata,
            litigation_session_id=litigation_session_id,
            step=step,
        )

    async def aget_by_session_id(self, session_id: str, user_id: str | None = None) -> QuerySet[ConversationHistory]:
        qs = ConversationHistory.objects.filter(session_id=session_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    async def adelete_by_session_id(self, session_id: str, user_id: str | None = None) -> tuple[int, dict[str, int]]:
        qs = ConversationHistory.objects.filter(session_id=session_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return await qs.adelete()
