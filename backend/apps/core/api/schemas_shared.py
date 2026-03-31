"""Module for schemas shared."""

from datetime import datetime
from typing import Any

from ninja import Schema
from pydantic import Field

from apps.core.api.schemas import SchemaMixin

__all__: list[str] = [
    "ClientIdentityDocLiteOut",
    "ClientLiteOut",
    "ReminderLiteOut",
    "ReminderOut",
]


class ClientIdentityDocLiteOut(Schema):
    doc_type: str
    file_path: str
    uploaded_at: datetime
    media_url: str | None = None

    @classmethod
    def from_model(cls, obj: Any) -> "ClientIdentityDocLiteOut":
        return cls(
            doc_type=getattr(obj, "doc_type", ""),
            file_path=getattr(obj, "file_path", ""),
            uploaded_at=obj.uploaded_at,
            media_url=obj.media_url if hasattr(obj, "media_url") else None,
        )


class ClientLiteOut(SchemaMixin, Schema):
    id: int
    name: str
    is_our_client: bool
    phone: str | None = None
    address: str | None = None
    client_type: str
    id_number: str | None = None
    legal_representative: str | None = None
    legal_representative_id_number: str | None = None
    client_type_label: str
    identity_docs: list[ClientIdentityDocLiteOut]

    @classmethod
    def from_model(cls, obj: Any) -> "ClientLiteOut":
        docs: list[ClientIdentityDocLiteOut] = []
        identity_docs = getattr(obj, "identity_docs", None)
        if identity_docs is not None and hasattr(identity_docs, "all"):
            docs = [ClientIdentityDocLiteOut.from_model(item) for item in identity_docs.all()]

        return cls(
            id=obj.id,
            name=getattr(obj, "name", ""),
            is_our_client=bool(getattr(obj, "is_our_client", False)),
            phone=getattr(obj, "phone", None),
            address=getattr(obj, "address", None),
            client_type=getattr(obj, "client_type", ""),
            id_number=getattr(obj, "id_number", None),
            legal_representative=getattr(obj, "legal_representative", None),
            legal_representative_id_number=getattr(obj, "legal_representative_id_number", None),
            client_type_label=SchemaMixin._get_display(obj, "client_type") or "",
            identity_docs=docs,
        )


class ReminderLiteOut(SchemaMixin, Schema):
    id: int
    contract_id: int | None = None
    case_log_id: int | None = None
    reminder_type: str
    reminder_type_label: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    due_at: str
    created_at: str
    updated_at: str

    @staticmethod
    def _read_value(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    @staticmethod
    def resolve_reminder_type_label(obj: Any) -> str:
        label = SchemaMixin._get_display(obj, "reminder_type")
        if label:
            return label
        from_obj = ReminderLiteOut._read_value(obj, "reminder_type_label")
        if from_obj is None:
            from_obj = ReminderLiteOut._read_value(obj, "reminder_type")
        return str(from_obj or "")

    @staticmethod
    def resolve_due_at(obj: Any) -> str:
        due_at = ReminderLiteOut._read_value(obj, "due_at")
        if isinstance(due_at, str):
            return due_at
        return SchemaMixin._resolve_datetime_iso(due_at) or ""

    @staticmethod
    def resolve_created_at(obj: Any) -> str:
        created_at = ReminderLiteOut._read_value(obj, "created_at")
        if isinstance(created_at, str):
            return created_at
        return SchemaMixin._resolve_datetime_iso(created_at) or ""

    @staticmethod
    def resolve_updated_at(obj: Any) -> str:
        updated_at = ReminderLiteOut._read_value(obj, "updated_at")
        if isinstance(updated_at, str):
            return updated_at
        return SchemaMixin._resolve_datetime_iso(updated_at) or ""


# Backward-compatible alias for modules that still import ReminderOut by name.
ReminderOut = ReminderLiteOut
