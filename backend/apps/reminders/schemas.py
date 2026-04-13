"""API schemas and serializers."""

from datetime import datetime
from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import Schema
from pydantic import Field, field_validator, model_validator

from apps.core.api.schemas import SchemaMixin

from .models import Reminder, ReminderType
from .services.validators import _CONTENT_MAX_LENGTH


def _validate_positive_id(value: int | None) -> int | None:
    if value is not None and (isinstance(value, bool) or value <= 0):
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
    case_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType
    content: str = Field(max_length=_CONTENT_MAX_LENGTH)
    due_at: datetime
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)

    @model_validator(mode="after")
    def validate_binding_exclusivity(self) -> "ReminderIn":
        selected_count = sum(target_id is not None for target_id in (self.contract_id, self.case_id, self.case_log_id))
        if selected_count > 1:
            raise ValueError(_("合同、案件、案件日志最多只能绑定一个"))
        return self


class ReminderUpdate(Schema):
    contract_id: int | None = None
    case_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType | None = None
    content: str | None = Field(None, max_length=_CONTENT_MAX_LENGTH)
    due_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)


class ReminderOut(SchemaMixin, Schema):
    id: int
    contract_id: int | None = None
    case_id: int | None = None
    case_log_id: int | None = None
    reminder_type: str
    reminder_type_label: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    due_at: str
    created_at: str
    updated_at: str

    @staticmethod
    def resolve_reminder_type_label(obj: Reminder) -> str:
        return SchemaMixin._get_display(obj, "reminder_type") or ""

    @staticmethod
    def resolve_due_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.due_at) or ""

    @staticmethod
    def resolve_created_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.created_at) or ""

    @staticmethod
    def resolve_updated_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.updated_at) or ""


class ReminderTypeItem(Schema):
    value: str
    label: str


def list_reminder_types() -> list[ReminderTypeItem]:
    return [ReminderTypeItem(value=value, label=str(label)) for value, label in ReminderType.choices]
