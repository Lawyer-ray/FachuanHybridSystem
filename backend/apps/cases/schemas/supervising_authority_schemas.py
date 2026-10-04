"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from .base import ModelSchema, Schema, SchemaMixin, SupervisingAuthority


class SupervisingAuthorityIn(Schema):
    name: str | None = None
    authority_type: str | None = None


class SupervisingAuthorityOut(ModelSchema, SchemaMixin):
    # created_at 允许 str：response= 端点对 _serialize_case 的 mode="json" dump 做
    # re-validation 时保持 ISO 字符串原样透传，避免 datetime 对象经 str() 改变线上格式
    created_at: datetime | str
    authority_type_display: str | None

    class Meta:
        model = SupervisingAuthority
        fields: ClassVar = ["id", "name", "authority_type"]

    @staticmethod
    def resolve_authority_type_display(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("authority_type_display")
        return obj.get_authority_type_display() if obj.authority_type else None

    @staticmethod
    def resolve_created_at(obj: Any) -> datetime | str | None:
        if isinstance(obj, dict):
            return obj.get("created_at")
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class SupervisingAuthorityUpdate(Schema):
    name: str | None = None
    authority_type: str | None = None


__all__: list[str] = [
    "SupervisingAuthorityIn",
    "SupervisingAuthorityOut",
    "SupervisingAuthorityUpdate",
]
