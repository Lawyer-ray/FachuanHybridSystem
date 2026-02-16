"""Business logic services."""

from __future__ import annotations

"""
诉讼AI对话会话服务(聚合入口)

本模块已拆分为:
- session_shared.py: 共享数据模型(SessionDTO, MessageDTO)
- session_lifecycle_service.py: 会话生命周期管理(创建、查询、状态更新、删除)
- session_message_service.py: 消息管理(添加、查询、批量操作、对话摘要)
"""


from typing import Any

from .session_lifecycle_service import SessionLifecycleService
from .session_message_service import SessionMessageService
from .session_shared import MessageDTO, SessionDTO

# Re-export 所有公共符号
__all__: list[str] = [
    "SessionDTO",
    "MessageDTO",
    "LitigationConversationSessionService",
    "SessionLifecycleService",
    "SessionMessageService",
]


class LitigationConversationSessionService:
    """诉讼AI对话会话服务 - 委托给专门的生命周期和消息服务"""

    def __init__(self) -> None:
        self._lifecycle = SessionLifecycleService()
        self._messages = SessionMessageService()

    # 暴露内部依赖以保持向后兼容
    @property
    def case_service(self) -> Any:
        return self._lifecycle.case_service

    @property
    def conversation_history_service(self) -> Any:
        return self._lifecycle.conversation_history_service

    @property
    def session_repo(self) -> Any:
        return self._lifecycle.session_repo

    # ---- 生命周期方法 ----

    def create_session(self, case_id: int, user_id: int | None = None) -> SessionDTO:
        return self._lifecycle.create_session(case_id, user_id)

    def get_session(self, session_id: str) -> SessionDTO:
        return self._lifecycle.get_session(session_id)

    def update_session_status(
        self, session_id: str, status: str, metadata_updates: dict[str, Any] | None = None
    ) -> SessionDTO:
        return self._lifecycle.update_session_status(session_id, status, metadata_updates)

    def get_recommended_document_types(self, case_id: int) -> list[str]:
        return self._lifecycle.get_recommended_document_types(case_id)

    def list_sessions(
        self,
        user_id: int | None = None,
        case_id: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._lifecycle.list_sessions(user_id, case_id, status, limit, offset)

    def delete_session(self, session_id: str, user: Any | None = None) -> None:
        return self._lifecycle.delete_session(session_id, user)

    # ---- 消息方法 ----

    def add_message(
        self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
    ) -> MessageDTO:
        return self._messages.add_message(session_id, role, content, metadata)

    def get_messages(self, session_id: str, limit: int = 50, offset: int = 0) -> list[MessageDTO]:
        return self._messages.get_messages(session_id, limit, offset)

    def get_message_count(self, session_id: str) -> int:
        return self._messages.get_message_count(session_id)

    def get_messages_batch(self, session_id: str, limit: int = 50, before_id: int | None = None) -> list[MessageDTO]:
        return self._messages.get_messages_batch(session_id, limit, before_id)

    def save_conversation_summary(self, session_id: str, summary: str) -> None:
        return self._messages.save_conversation_summary(session_id, summary)

    def get_conversation_summary(self, session_id: str) -> str | None:
        return self._messages.get_conversation_summary(session_id)

    def add_messages_batch(self, session_id: str, messages: list[dict[str, Any]]) -> list[MessageDTO]:
        return self._messages.add_messages_batch(session_id, messages)

    # ---- 内部转换方法(向后兼容) ----

    def _to_session_dto(self, session: Any) -> SessionDTO:
        return self._lifecycle._to_session_dto(session)

    def _to_message_dto(self, message: Any) -> MessageDTO:
        return self._messages._to_message_dto(message)
