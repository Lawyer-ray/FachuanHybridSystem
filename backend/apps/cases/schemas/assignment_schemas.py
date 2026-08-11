"""API schemas and serializers."""

from __future__ import annotations

from typing import Any, ClassVar

from .base import CaseAssignment, ModelSchema, Schema
from .lawyer_schemas import LawyerOutFromDTO


class CaseAssignmentIn(Schema):
    case_id: int
    lawyer_id: int


class CaseAssignmentUpdate(Schema):
    case_id: int | None = None
    lawyer_id: int | None = None


class CaseAssignmentOut(ModelSchema):
    lawyer_detail: LawyerOutFromDTO

    class Meta:
        model = CaseAssignment
        fields: ClassVar = ["id", "case", "lawyer"]

    @staticmethod
    def resolve_lawyer_detail(obj: Any) -> LawyerOutFromDTO:
        # Dict/Pydantic model (re-validation) — return pre-computed value
        if isinstance(obj, dict):
            detail = obj.get("lawyer_detail")
            if isinstance(detail, dict):
                return LawyerOutFromDTO(**detail)
            return detail  # type: ignore[return-value]
        # Django model — compute from FK
        lawyer = getattr(obj, "lawyer", None)
        if lawyer is not None and hasattr(lawyer, "_meta"):
            return LawyerOutFromDTO.from_model(lawyer)
        # Pydantic model or fallback — return pre-computed value
        detail = getattr(obj, "lawyer_detail", None)
        if detail is not None:
            if isinstance(detail, dict):
                return LawyerOutFromDTO(**detail)
            return detail  # type: ignore[no-any-return]
        lawyer_id = getattr(obj, "lawyer_id", None)
        if lawyer_id:
            return LawyerOutFromDTO(id=lawyer_id, username=f"lawyer_{lawyer_id}", real_name=None, phone=None)
        raise ValueError("无法解析 lawyer_detail")


class CaseAssignmentCreate(Schema):
    lawyer_id: int


__all__: list[str] = [
    "CaseAssignmentCreate",
    "CaseAssignmentIn",
    "CaseAssignmentOut",
    "CaseAssignmentUpdate",
]
