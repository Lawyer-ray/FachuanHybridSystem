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
    # uploaded_at 允许 str：response= 端点对 mode="json" dump re-validation 时保持
    # ISO 字符串原样透传，避免 datetime 对象经 str() 改变线上格式
    uploaded_at: datetime | str

    class Meta:
        model = CaseLogAttachment
        fields: ClassVar = ["id", "log", "original_filename"]

    @staticmethod
    def resolve_file_path(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("file_path")
        return SchemaMixin._get_file_path(obj.file)

    @staticmethod
    def resolve_media_url(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("media_url")
        return SchemaMixin._get_file_url(obj.file)

    @staticmethod
    def resolve_uploaded_at(obj: Any) -> datetime | str:
        if isinstance(obj, dict):
            value = obj.get("uploaded_at")
            return value if value is not None else ""
        return SchemaMixin._resolve_datetime(getattr(obj, "uploaded_at", None)) or ""


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
    # created_at / updated_at 允许 str：response= 端点对 mode="json" dump 做
    # re-validation 时保持 ISO 字符串原样透传，避免 datetime 对象经 str() 改变线上格式
    created_at: datetime | str
    updated_at: datetime | str

    class Meta:
        model = CaseLog
        fields: ClassVar = [
            "id",
            "case",
            "content",
            "actor",
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
    def resolve_created_at(obj: Any) -> datetime | str | None:
        if isinstance(obj, dict):
            # re-validation：mode="json" dump 的 ISO 字符串原样返回（union 字段保留
            # str，不转 datetime），保证响应渲染与裸 dict 路径逐字节一致
            return obj.get("created_at")
        value = getattr(obj, "created_at", None)
        if value is not None and not hasattr(value, "year"):
            # value is a string or other — try datetime parsing
            return SchemaMixin._resolve_datetime(value)
        return value

    @staticmethod
    def resolve_updated_at(obj: Any) -> datetime | str | None:
        if isinstance(obj, dict):
            return obj.get("updated_at")
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
