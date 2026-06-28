"""工作人员联系方式 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.contacts.models import CaseContact
from apps.core.api.schemas import SchemaMixin


class CaseContactIn(Schema):
    case_id: int
    authority_id: int | None = None
    name: str
    role: str
    phone: str | None = None
    address: str | None = None
    stage: str | None = None
    note: str | None = None


class CaseContactOut(ModelSchema, SchemaMixin):
    role_display: str | None
    stage_display: str | None
    authority_name: str | None
    case_id: int
    authority_id: int | None

    class Meta:
        model = CaseContact
        fields: ClassVar = [
            "id",
            "name",
            "role",
            "phone",
            "address",
            "stage",
            "note",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_case_id(obj: Any) -> int:
        if isinstance(obj, dict):
            return obj.get("case_id", 0)  # type: ignore[no-any-return]
        return obj.case_id  # type: ignore[no-any-return]

    @staticmethod
    def resolve_authority_id(obj: Any) -> int | None:
        if isinstance(obj, dict):
            return obj.get("authority_id")
        return obj.authority_id

    @staticmethod
    def resolve_role_display(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("role_display")
        return obj.get_role_display()

    @staticmethod
    def resolve_stage_display(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("stage_display")
        return obj.get_stage_display() if obj.stage else None

    @staticmethod
    def resolve_authority_name(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("authority_name")
        return obj.authority.name if obj.authority else None

    @staticmethod
    def resolve_created_at(obj: Any) -> datetime | None:
        if isinstance(obj, dict):
            return obj.get("created_at")
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: Any) -> datetime | None:
        if isinstance(obj, dict):
            return obj.get("updated_at")
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))


class CaseContactUpdate(Schema):
    authority_id: int | None = None
    name: str | None = None
    role: str | None = None
    phone: str | None = None
    address: str | None = None
    stage: str | None = None
    note: str | None = None


class CaseContactSearchResult(Schema):
    authority_name: str | None = None
    name: str
    role: str
    role_display: str | None = None
    phone: str | None = None
    address: str | None = None
    occurrence_count: int = 1
    case_ids: list[int] = []


__all__: list[str] = [
    "CaseContactIn",
    "CaseContactOut",
    "CaseContactSearchResult",
    "CaseContactUpdate",
]
