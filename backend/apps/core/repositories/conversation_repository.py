"""
ConversationHistory Repository

封装 ConversationHistory 模型的数据访问操作
"""

from typing import Any

from apps.core.models.conversation import ConversationHistory


class ConversationHistoryRepository:
    """对话历史数据访问层"""

    def create(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationHistory:
        """创建对话记录"""
        return ConversationHistory.objects.create(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )

    def get_by_session(self, session_id: str, limit: int = 20) -> list[ConversationHistory]:
        """根据 session_id 获取对话历史"""
        return list(ConversationHistory.objects.filter(session_id=session_id).order_by("created_at")[:limit])

    def get_all(self) -> list[ConversationHistory]:
        """获取所有对话记录"""
        return list(ConversationHistory.objects.all())

    def filter_by_user(self, user_id: str) -> list[ConversationHistory]:
        """根据用户ID过滤"""
        return list(ConversationHistory.objects.filter(user_id=user_id))

    def filter_by_role(self, role: str) -> list[ConversationHistory]:
        """根据角色过滤"""
        return list(ConversationHistory.objects.filter(role=role))
