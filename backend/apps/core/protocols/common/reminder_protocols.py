"""Module for reminder protocols."""

from datetime import datetime
from typing import Any, Protocol

from apps.core.dtos import ReminderDTO, ReminderTypeDTO


class IReminderService(Protocol):
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
