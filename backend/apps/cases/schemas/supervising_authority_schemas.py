"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from .base import ModelSchema, Schema, SchemaMixin, SupervisingAuthority


class SupervisingAuthorityIn(Schema):
    name: str | None = None
    authority_type: str | None = None


class SupervisingAuthorityOut(ModelSchema, SchemaMixin):
    authority_type_display: str | None

    class Meta:
        model = SupervisingAuthority
        fields: ClassVar = ["id", "name", "authority_type", "created_at"]

    @staticmethod
    def resolve_authority_type_display(obj: SupervisingAuthority) -> str | None:
        return obj.get_authority_type_display() if obj.authority_type else None

    @staticmethod
    def resolve_created_at(obj: SupervisingAuthority) -> datetime | None:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class SupervisingAuthorityUpdate(Schema):
    name: str | None = None
    authority_type: str | None = None


__all__: list[str] = [
    "SupervisingAuthorityIn",
    "SupervisingAuthorityOut",
    "SupervisingAuthorityUpdate",
]
