"""API schemas and serializers."""

from __future__ import annotations

from typing import Any, ClassVar

from .base import CaseLog, CaseLogAttachment, ModelSchema, ReminderOut, Schema, SchemaMixin


class CaseLogIn(Schema):
    case_id: int
    content: str


class CaseLogUpdate(Schema):
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
    def resolve_uploaded_at(obj: CaseLogAttachment) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "uploaded_at", None))


class CaseLogActorOut(Schema):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None

    @classmethod
    def from_model(cls, lawyer: Any) -> CaseLogActorOut:
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
    def resolve_reminders(obj: CaseLog) -> Any:
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
    def resolve_created_at(obj: CaseLog) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: CaseLog) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))


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


class CaseLogCreate(Schema):
    content: str
    reminder_type: str | None = None
    reminder_time: str | None = None


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
