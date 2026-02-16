"""API schemas and serializers."""

from typing import ClassVar, Optional

from .base import CaseNumber, ModelSchema, Optional, Schema, SchemaMixin


class CaseNumberIn(Schema):
    case_id: int
    number: str
    remarks: Optional[str] = None


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
    number: Optional[str] = None
    remarks: Optional[str] = None


__all__: list[str] = ["CaseNumberIn", "CaseNumberOut", "CaseNumberUpdate"]
