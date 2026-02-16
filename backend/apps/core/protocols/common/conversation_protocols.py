"""Module for conversation protocols."""

from typing import Any, Protocol

from apps.core.dtos import ConversationHistoryDTO


class IConversationHistoryService(Protocol):
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
    ) -> ConversationHistoryDTO: ...

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
    ) -> list[ConversationHistoryDTO]: ...

    def count_messages_internal(
        self,
        *,
        session_id: str | None = None,
        litigation_session_id: int | None = None,
    ) -> int: ...

    def count_messages_by_litigation_session_ids_internal(
        self, *, litigation_session_ids: list[int]
    ) -> dict[int, int]: ...


class ICaseChatService(Protocol):
    def send_message_to_case_chat(self, case_id: int, message: str, files: list[str] | None = None) -> bool: ...

    def get_case_chat_id(self, case_id: int) -> str | None: ...


class IEvidenceListPlaceholderService(Protocol):
    def get_evidence_list_context(self, evidence_list_id: int) -> dict[str, Any]: ...

    def get_evidence_list_name(self, evidence_list: Any, case_data: dict[str, Any]) -> str: ...

    def get_parties_brief(self, case_data: dict[str, Any]) -> str: ...

    def get_evidence_items(self, evidence_list: Any) -> list[dict[str, Any]]: ...

    def get_signature_info(self, case_data: dict[str, Any]) -> str: ...
