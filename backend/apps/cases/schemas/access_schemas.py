"""API schemas and serializers."""

from typing import Any, ClassVar, Optional

from .base import CaseAccessGrant, ModelSchema, Optional, Schema, SchemaMixin


class CaseAccessGrantIn(Schema):
    case_id: int
    grantee_id: int


class CaseAccessGrantOut(ModelSchema, SchemaMixin):
    class Meta:
        model = CaseAccessGrant
        fields: ClassVar = ["id", "case", "grantee", "created_at"]

    @staticmethod
    def resolve_created_at(obj: CaseAccessGrant) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class CaseAccessGrantUpdate(Schema):
    case_id: Optional[int] = None
    grantee_id: Optional[int] = None


__all__: list[str] = ["CaseAccessGrantIn", "CaseAccessGrantOut", "CaseAccessGrantUpdate"]
