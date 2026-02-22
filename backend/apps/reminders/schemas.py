"""API schemas and serializers."""

from datetime import datetime
from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import Schema
from pydantic import field_validator, model_validator

from apps.core.schemas import SchemaMixin

from .models import Reminder, ReminderType


def _validate_positive_id(value: int | None) -> int | None:
    if value is not None and value <= 0:
        raise ValueError(_("ID 必须为正整数"))
    return value


def _validate_content_not_blank(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(_("提醒事项不能为空"))
    return normalized


class ReminderIn(Schema):
    contract_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType
    content: str
    due_at: datetime
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)

    @model_validator(mode="after")
    def validate_binding_exclusivity(self) -> "ReminderIn":
        """contract_id 和 case_log_id 互斥校验。"""
        both_none = self.contract_id is None and self.case_log_id is None
        both_set = self.contract_id is not None and self.case_log_id is not None
        if both_none or both_set:
            raise ValueError(_("必须且只能绑定合同或案件日志之一"))
        return self


class ReminderUpdate(Schema):
    contract_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType | None = None
    content: str | None = None
    due_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)


class ReminderOut(SchemaMixin, Schema):
    id: int
    contract_id: int | None = None
    case_log_id: int | None = None
    reminder_type: str
    reminder_type_label: str
    content: str
    metadata: dict[str, Any] | None = None
    due_at: str | None = None
    created_at: str | None = None

    @staticmethod
    def resolve_contract_id(obj: Reminder) -> int | None:
        return obj.contract_id

    @staticmethod
    def resolve_case_log_id(obj: Reminder) -> int | None:
        return obj.case_log_id

    @staticmethod
    def resolve_reminder_type_label(obj: Reminder) -> str:
        return SchemaMixin._get_display(obj, "reminder_type") or ""

    @staticmethod
    def resolve_due_at(obj: Reminder) -> str | None:
        return SchemaMixin._resolve_datetime_iso(obj.due_at)

    @staticmethod
    def resolve_created_at(obj: Reminder) -> str | None:
        return SchemaMixin._resolve_datetime_iso(obj.created_at)


class ReminderTypeItem(Schema):
    value: str
    label: str


def list_reminder_types() -> list[ReminderTypeItem]:
    return [ReminderTypeItem(value=value, label=str(label)) for value, label in ReminderType.choices]
