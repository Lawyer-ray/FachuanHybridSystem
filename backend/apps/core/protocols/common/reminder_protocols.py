"""Module for reminder protocols."""

from datetime import datetime
from typing import Any, Protocol

from apps.core.dto import ReminderDTO, ReminderTypeDTO


class IReminderService(Protocol):
    def create_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        reminder_type: str,
        content: str,
        reminder_time: datetime,
        user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReminderDTO: ...

    def upsert_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        reminder_type: str,
        content: str,
        reminder_time: datetime,
        user_id: int | None = None,
        metadata_source: str | None = None,
    ) -> ReminderDTO: ...

    def clear_case_log_reminder_internal(
        self,
        *,
        case_log_id: int,
        metadata_source: str | None = None,
    ) -> bool: ...

    def create_reminder_internal(
        self,
        case_log_id: int,
        reminder_type: str,
        reminder_time: datetime | None,
        user_id: int | None = None,
    ) -> ReminderDTO | None: ...

    def get_reminder_type_by_code_internal(self, code: str) -> ReminderTypeDTO | None: ...

    def get_reminder_type_for_document_internal(self, document_type: str) -> ReminderTypeDTO | None: ...

    def get_existing_reminder_times_internal(self, case_log_id: int, reminder_type: str) -> set[datetime]: ...

    def create_contract_reminders_internal(self, *, contract_id: int, reminders: list[dict[str, Any]]) -> int: ...

    def create_case_log_reminders_internal(self, *, case_log_id: int, reminders: list[dict[str, Any]]) -> int: ...

    def export_contract_reminders_internal(self, *, contract_id: int) -> list[dict[str, Any]]: ...

    def export_case_log_reminders_internal(self, *, case_log_id: int) -> list[dict[str, Any]]: ...

    def export_case_log_reminders_batch_internal(
        self, *, case_log_ids: list[int]
    ) -> dict[int, list[dict[str, Any]]]: ...

    def get_latest_case_log_reminder_internal(self, *, case_log_id: int) -> dict[str, Any] | None: ...
