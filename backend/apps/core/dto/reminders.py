"""Module for reminders."""

from dataclasses import dataclass


@dataclass
class ReminderDTO:
    id: int
    case_log_id: int | None
    reminder_type: str
    reminder_time: str
    contract_id: int | None = None
    case_id: int | None = None
    created_at: str | None = None


@dataclass
class ReminderTypeDTO:
    id: int
    code: str
    name: str
    description: str | None = None
