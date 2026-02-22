"""API schemas and serializers."""

from __future__ import annotations

from typing import ClassVar

from .base import CaseNumber, ModelSchema, Schema, SchemaMixin


class CaseNumberIn(Schema):
    case_id: int
    number: str
    remarks: str | None = None


class CaseNumberOut(ModelSchema, SchemaMixin):
    class Meta:
        model = CaseNumber
        fields: ClassVar = [
            "id",
            "number",
            "remarks",
            "created_at",
        ]

    @staticmethod
    def resolve_created_at(obj: CaseNumber) -> str | None:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))


class CaseNumberUpdate(Schema):
    number: str | None = None
    remarks: str | None = None


__all__: list[str] = ["CaseNumberIn", "CaseNumberOut", "CaseNumberUpdate"]
