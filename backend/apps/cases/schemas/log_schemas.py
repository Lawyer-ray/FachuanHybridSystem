"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Protocol

from apps.reminders.models import ReminderType
from django.utils.translation import gettext_lazy as _
from pydantic import model_validator

from .base import CaseLog, CaseLogAttachment, ModelSchema, ReminderOut, Schema, SchemaMixin


class LawyerLike(Protocol):
    id: int
    username: str
    real_name: str | None
    phone: str | None


ReminderPayload = dict[str, object]


def _validate_reminder_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(_("提醒类型不能为空"))
    if normalized not in ReminderType.values:
        raise ValueError(_("无效的提醒类型"))
    return normalized


class _CaseLogReminderMixin(Schema):
    reminder_type: str | None = None
    reminder_time: datetime | None = None

    @model_validator(mode="after")
    def validate_reminder_fields(self) -> "_CaseLogReminderMixin":
        fields_set = getattr(self, "model_fields_set", set())
        reminder_type_set = "reminder_type" in fields_set
        reminder_time_set = "reminder_time" in fields_set

        if reminder_type_set != reminder_time_set:
            raise ValueError(_("提醒类型和提醒时间必须同时提供"))

        if reminder_type_set and reminder_time_set:
            if (self.reminder_type is None) != (self.reminder_time is None):
                raise ValueError(_("提醒类型和提醒时间必须同时为空或同时有值"))

        self.reminder_type = _validate_reminder_type(self.reminder_type)
        return self


class CaseLogCreate(_CaseLogReminderMixin):
    content: str

class CaseLogIn(CaseLogCreate):
    case_id: int


class CaseLogUpdate(_CaseLogReminderMixin):
    case_id: int | None = None
    content: str | None = None


class CaseLogAttachmentOut(ModelSchema, SchemaMixin):
    file_path: str | None
    media_url: str | None

    class Meta:
        model = CaseLogAttachment
        fields: ClassVar = ["id", "log", "uploaded_at"]

    @staticmethod
    def resolve_file_path(obj: CaseLogAttachment) -> str | None:
        return SchemaMixin._get_file_path(obj.file)

    @staticmethod
    def resolve_media_url(obj: CaseLogAttachment) -> str | None:
        return SchemaMixin._get_file_url(obj.file)

    @staticmethod
    def resolve_uploaded_at(obj: CaseLogAttachment) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "uploaded_at", None))


class CaseLogActorOut(Schema):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None

    @classmethod
    def from_model(cls, lawyer: LawyerLike) -> CaseLogActorOut:
        return cls(
            id=lawyer.id,
            username=lawyer.username,
            real_name=getattr(lawyer, "real_name", None) or None,
            phone=getattr(lawyer, "phone", None) or None,
        )


class CaseLogOut(ModelSchema, SchemaMixin):
    attachments: list[CaseLogAttachmentOut]
    reminders: list[ReminderOut]
    actor_detail: CaseLogActorOut
    reminder_type: str | None = None
    reminder_time: str | None = None

    class Meta:
        model = CaseLog
        fields: ClassVar = [
            "id",
            "case",
            "content",
            "actor",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_attachments(obj: CaseLog) -> list[CaseLogAttachmentOut]:
        return list(obj.attachments.all())

    @staticmethod
    def resolve_reminders(obj: CaseLog) -> list[ReminderPayload]:
        from apps.core.interfaces import ServiceLocator

        reminder_service = ServiceLocator.get_reminder_service()
        return reminder_service.export_case_log_reminders_internal(case_log_id=obj.id)

    @staticmethod
    def resolve_actor(obj: CaseLog) -> int:
        return obj.actor_id

    @staticmethod
    def resolve_actor_detail(obj: CaseLog) -> CaseLogActorOut:
        actor = getattr(obj, "actor", None)
        if actor is not None:
            return CaseLogActorOut.from_model(actor)
        return CaseLogActorOut(id=obj.actor_id, username=f"lawyer_{obj.actor_id}", real_name=None, phone=None)

    @staticmethod
    def resolve_created_at(obj: CaseLog) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: CaseLog) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))

    @staticmethod
    def _resolve_primary_reminder(obj: CaseLog) -> ReminderPayload | None:
        reminders = obj.reminder_entries if hasattr(obj, "reminder_entries") else []
        if not reminders:
            return None

        for reminder in reversed(reminders):
            metadata = reminder.get("metadata") or {}
            if isinstance(metadata, dict) and metadata.get("source") == "case_log_api":
                return reminder
        return reminders[-1]

    @staticmethod
    def resolve_reminder_type(obj: CaseLog) -> str | None:
        reminder = CaseLogOut._resolve_primary_reminder(obj)
        if reminder is None:
            return None
        return str(reminder.get("reminder_type") or "") or None

    @staticmethod
    def resolve_reminder_time(obj: CaseLog) -> str | None:
        reminder = CaseLogOut._resolve_primary_reminder(obj)
        if reminder is None:
            return None
        return SchemaMixin._resolve_datetime_iso(reminder.get("due_at"))


class CaseLogAttachmentIn(Schema):
    log_id: int


class CaseLogAttachmentUpdate(Schema):
    log_id: int | None = None


class CaseLogVersionOut(Schema):
    id: int
    content: str
    version_at: str
    actor_id: int


class CaseLogAttachmentCreate(Schema):
    pass


__all__: list[str] = [
    "CaseLogActorOut",
    "CaseLogAttachmentCreate",
    "CaseLogAttachmentIn",
    "CaseLogAttachmentOut",
    "CaseLogAttachmentUpdate",
    "CaseLogCreate",
    "CaseLogIn",
    "CaseLogOut",
    "CaseLogUpdate",
    "CaseLogVersionOut",
]
