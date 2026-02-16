"""API schemas and serializers."""

from typing import Any, ClassVar, Optional

from .base import ModelSchema, Optional, Schema, SchemaMixin, SupervisingAuthority


class SupervisingAuthorityIn(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None


class SupervisingAuthorityOut(ModelSchema, SchemaMixin):
    authority_type_display: str | None

    class Meta:
        model = SupervisingAuthority
        fields: ClassVar = ["id", "name", "authority_type", "created_at"]

    @staticmethod
    def resolve_authority_type_display(obj: SupervisingAuthority) -> str | None:
        return obj.get_authority_type_display() if obj.authority_type else None

    @staticmethod
    def resolve_created_at(obj: SupervisingAuthority) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class SupervisingAuthorityUpdate(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None


__all__: list[str] = [
    "SupervisingAuthorityIn",
    "SupervisingAuthorityOut",
    "SupervisingAuthorityUpdate",
]
