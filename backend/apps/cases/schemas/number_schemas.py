"""API schemas and serializers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from .base import CaseNumber, ModelSchema, Schema, SchemaMixin


class CaseNumberIn(Schema):
    case_id: int
    number: str
    remarks: str | None = None


class CaseNumberOut(ModelSchema, SchemaMixin):
    # created_at 允许 str：response= 端点对 mode="json" dump re-validation 时保持
    # ISO 字符串原样透传，避免 datetime 对象经 str() 改变线上格式
    created_at: datetime | str

    class Meta:
        model = CaseNumber
        fields: ClassVar = [
            "id",
            "number",
            "remarks",
        ]

    @staticmethod
    def resolve_created_at(obj: Any) -> datetime | str | None:
        if isinstance(obj, dict):
            return obj.get("created_at")
        # 模型路径返回 datetime（与原 ISO 字符串经 datetime 字段强转的结果等价，
        # 各消费端渲染不变），使 re-validation 的 str 输入可原样保留
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class CaseNumberUpdate(Schema):
    number: str | None = None
    remarks: str | None = None


__all__: list[str] = ["CaseNumberIn", "CaseNumberOut", "CaseNumberUpdate"]
