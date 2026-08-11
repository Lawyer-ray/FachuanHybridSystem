"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Protocol

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
    from apps.reminders.models import ReminderType

    normalized = value.strip()
    if not normalized:
        raise ValueError("提醒类型不能为空")
    if normalized not in ReminderType.values:
        raise ValueError("无效的提醒类型")
    return normalized


class _CaseLogReminderMixin(Schema):
    reminder_type: str | None = None
    reminder_time: datetime | None = None

    @model_validator(mode="after")
    def validate_reminder_fields(self) -> _CaseLogReminderMixin:
        # Pydantic v2: self.field = ... in model_validator(mode="after")
        # mutates model_fields_set, leaking defaults into exclude_unset=True.
        # Snapshot the original set and restore after assignments.
        original_fields_set = set(self.model_fields_set)
        reminder_type_set = "reminder_type" in original_fields_set
        reminder_time_set = "reminder_time" in original_fields_set
        if reminder_type_set != reminder_time_set:
            raise ValueError("提醒类型和提醒时间必须同时提供")
        if reminder_type_set and reminder_time_set:
            if (self.reminder_type is None) != (self.reminder_time is None):
                raise ValueError("提醒类型和提醒时间必须同时为空或同时有值")
        self.reminder_type = _validate_reminder_type(self.reminder_type)
        object.__setattr__(self, "__pydantic_fields_set__", original_fields_set)
        return self


class CaseLogIn(_CaseLogReminderMixin):
    case_id: int
    content: str


class CaseLogUpdate(_CaseLogReminderMixin):
    case_id: int | None = None
    content: str | None = None


class CaseLogAttachmentOut(ModelSchema, SchemaMixin):
    file_path: str | None
    media_url: str | None

    class Meta:
        model = CaseLogAttachment
        fields: ClassVar = ["id", "log", "original_filename", "uploaded_at"]

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
    def resolve_attachments(obj: Any) -> list[Any]:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            return obj.get("attachments", [])  # type: ignore[no-any-return]
        value = getattr(obj, "attachments", None)
        if value is None:
            return []
        if hasattr(value, "all"):
            return list(value.all())
        return list(value)

    @staticmethod
    def resolve_reminders(obj: Any) -> list[Any]:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            return obj.get("reminders", [])  # type: ignore[no-any-return]
        value = getattr(obj, "reminder_entries", None)
        if value is not None:
            return value  # type: ignore[no-any-return]
        # Pydantic model — return pre-computed value
        return getattr(obj, "reminders", []) or []

    @staticmethod
    def _resolve_primary_reminder(obj: Any) -> ReminderPayload | None:
        if isinstance(obj, dict):
            reminders: list[Any] = obj.get("reminders", [])
        else:
            # 优先使用 reminder_entries（@property，返回 list，可能为空）
            entries = getattr(obj, "reminder_entries", None)
            if entries is None:
                # Pydantic 模型或无 reminder_entries 属性 — 取预计算字段
                fallback = getattr(obj, "reminders", None)
                if fallback is None:
                    reminders = []
                elif isinstance(fallback, list):
                    reminders = fallback
                else:
                    # RelatedManager — materialize 避免后续 reversed() 失败
                    reminders = list(fallback.all())
            else:
                reminders = entries
        if not reminders:
            return None
        for reminder in reversed(reminders):
            metadata = reminder.get("metadata") or {}
            if isinstance(metadata, dict) and metadata.get("source") == "case_log_api":
                return reminder  # type: ignore[no-any-return]
        return reminders[-1]  # type: ignore[no-any-return]

    @staticmethod
    def resolve_reminder_type(obj: Any) -> str | None:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            return obj.get("reminder_type")
        if not hasattr(obj, "reminder_entries"):
            return getattr(obj, "reminder_type", None)
        reminder = CaseLogOut._resolve_primary_reminder(obj)
        if reminder is None:
            return None
        return str(reminder.get("reminder_type") or "") or None

    @staticmethod
    def resolve_reminder_time(obj: Any) -> str | None:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            return obj.get("reminder_time")
        if not hasattr(obj, "reminder_entries"):
            return getattr(obj, "reminder_time", None)
        reminder = CaseLogOut._resolve_primary_reminder(obj)
        if reminder is None:
            return None
        return SchemaMixin._resolve_datetime_iso(reminder.get("due_at"))

    @staticmethod
    def resolve_actor(obj: Any) -> int:
        if isinstance(obj, dict):
            return obj.get("actor_id", 0)  # type: ignore[no-any-return]
        return getattr(obj, "actor_id", 0)

    @staticmethod
    def resolve_actor_detail(obj: Any) -> CaseLogActorOut:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            detail = obj.get("actor_detail")
            if isinstance(detail, dict):
                return CaseLogActorOut(**detail)
            return detail  # type: ignore[return-value]
        # Django model — compute from FK
        actor = getattr(obj, "actor", None)
        if actor is not None and hasattr(actor, "_meta"):
            return CaseLogActorOut.from_model(actor)
        # Pydantic model — return pre-computed value
        detail = getattr(obj, "actor_detail", None)
        if detail is not None:
            if isinstance(detail, dict):
                return CaseLogActorOut(**detail)
            return detail  # type: ignore[no-any-return]
        actor_id = getattr(obj, "actor_id", None)
        if actor_id:
            return CaseLogActorOut(id=actor_id, username=f"lawyer_{actor_id}", real_name=None, phone=None)
        raise ValueError("无法解析 actor_detail")

    @staticmethod
    def resolve_created_at(obj: Any) -> datetime | None:
        if isinstance(obj, dict):
            value = obj.get("created_at")
        else:
            value = getattr(obj, "created_at", None)
        # During re-validation, value is already a datetime/str — return as-is
        if value is not None and not hasattr(value, "year"):
            # value is a string or other — try datetime parsing
            return SchemaMixin._resolve_datetime(value)
        return value

    @staticmethod
    def resolve_updated_at(obj: Any) -> datetime | None:
        if isinstance(obj, dict):
            value = obj.get("updated_at")
        else:
            value = getattr(obj, "updated_at", None)
        if value is not None and not hasattr(value, "year"):
            return SchemaMixin._resolve_datetime(value)
        return value


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


class CaseLogCreate(_CaseLogReminderMixin):
    content: str


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
