"""API schemas and serializers."""

from datetime import datetime
from typing import Any, ClassVar

from django.utils.translation import gettext_lazy as _
from ninja import ModelSchema, Schema
from pydantic import field_validator, model_validator

from apps.core.schemas import SchemaMixin

from .models import Reminder, ReminderType


class ReminderIn(Schema):
    contract_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType
    content: str
    due_at: datetime
    metadata: dict[str, Any] | None = None

    @field_validator("contract_id", "case_log_id")
    @classmethod
    def validate_positive_target_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError(_("ID 必须为正整数"))
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_("提醒事项不能为空"))
        return normalized

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

    @field_validator("contract_id", "case_log_id")
    @classmethod
    def validate_positive_target_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError(_("ID 必须为正整数"))
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(_("提醒事项不能为空"))
        return normalized

    @model_validator(mode="after")
    def validate_binding_exclusivity(self) -> "ReminderUpdate":
        """contract_id 和 case_log_id 互斥校验（仅当两者都被显式提交时）。"""
        fields_set = self.model_fields_set
        if "contract_id" in fields_set and "case_log_id" in fields_set:
            both_none = self.contract_id is None and self.case_log_id is None
            both_set = self.contract_id is not None and self.case_log_id is not None
            if both_none or both_set:
                raise ValueError(_("必须且只能绑定合同或案件日志之一"))
        return self


class ReminderOut(ModelSchema, SchemaMixin):
    reminder_type_label: str
    due_at: str | None
    created_at: str | None

    class Meta:
        model = Reminder
        fields: ClassVar = [
            "id",
            "contract",
            "case_log",
            "reminder_type",
            "content",
            "metadata",
            "due_at",
            "created_at",
        ]

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
