"""API schemas and serializers."""

from __future__ import annotations

from typing import ClassVar, Optional

from .base import CaseAssignment, ModelSchema, Optional, Schema
from .lawyer_schemas import LawyerOutFromDTO


class CaseAssignmentIn(Schema):
    case_id: int
    lawyer_id: int


class CaseAssignmentUpdate(Schema):
    case_id: Optional[int] = None
    lawyer_id: Optional[int] = None


class CaseAssignmentOut(ModelSchema):
    lawyer_detail: LawyerOutFromDTO

    class Meta:
        model = CaseAssignment
        fields: ClassVar = ["id", "case", "lawyer"]

    @staticmethod
    def resolve_lawyer_detail(obj: CaseAssignment) -> LawyerOutFromDTO:
        lawyer = getattr(obj, "lawyer", None)
        if lawyer is not None:
            return LawyerOutFromDTO.from_model(lawyer)
        return LawyerOutFromDTO(id=obj.lawyer_id, username=f"lawyer_{obj.lawyer_id}", real_name=None, phone=None)


class CaseAssignmentCreate(Schema):
    lawyer_id: int


__all__: list[str] = [
    "CaseAssignmentCreate",
    "CaseAssignmentIn",
    "CaseAssignmentOut",
    "CaseAssignmentUpdate",
]
