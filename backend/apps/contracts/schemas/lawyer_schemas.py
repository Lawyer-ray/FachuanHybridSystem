"""API schemas and serializers."""

from __future__ import annotations

"""
Contract Schemas - Lawyer, Reminder, Case

律师、提醒和案件相关的 Schema 定义.
"""

from typing import Any

from ninja import Schema

from apps.core.schemas import SchemaMixin


class LawyerOut(Schema):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    law_firm: int | None = None
    law_firm_name: str | None = None

    @classmethod
    def from_model(cls, obj: Any) -> LawyerOut:
        law_firm = getattr(obj, "law_firm", None)
        return cls(
            id=obj.id,
            username=getattr(obj, "username", ""),
            real_name=getattr(obj, "real_name", None) or None,
            phone=getattr(obj, "phone", None) or None,
            is_admin=getattr(obj, "is_admin", None),
            is_active=getattr(obj, "is_active", None),
            law_firm=getattr(obj, "law_firm_id", None),
            law_firm_name=getattr(law_firm, "name", None) if law_firm is not None else None,
        )

    @classmethod
    def from_dto(cls, dto: Any) -> LawyerOut:
        return cls(
            id=dto.id,
            username=getattr(dto, "username", ""),
            real_name=getattr(dto, "real_name", None) or None,
            phone=getattr(dto, "phone", None) or None,
            is_admin=getattr(dto, "is_admin", None),
            is_active=getattr(dto, "is_active", None),
            law_firm=getattr(dto, "law_firm_id", None),
            law_firm_name=getattr(dto, "law_firm_name", None),
        )


class CaseOut(SchemaMixin, Schema):
    id: int
    name: str
    status: str | None = None
    status_label: str | None = None
    case_type: str | None = None
    start_date: str | None = None
    effective_date: str | None = None
    target_amount: float | None = None
    preservation_amount: float | None = None
    cause_of_action: str | None = None
    current_stage: str | None = None
    current_stage_label: str | None = None

    @classmethod
    def from_model(cls, obj: Any) -> CaseOut:
        target_amount = getattr(obj, "target_amount", None)
        preservation_amount = getattr(obj, "preservation_amount", None)
        return cls(
            id=obj.id,
            name=getattr(obj, "name", ""),
            status=getattr(obj, "status", None),
            status_label=(
                obj.get_status_display()
                if hasattr(obj, "get_status_display") and getattr(obj, "status", None)
                else None
            ),
            case_type=getattr(obj, "case_type", None),
            start_date=SchemaMixin._resolve_datetime_iso(getattr(obj, "start_date", None)),
            effective_date=SchemaMixin._resolve_datetime_iso(getattr(obj, "effective_date", None)),
            target_amount=float(target_amount) if target_amount is not None else None,
            preservation_amount=float(preservation_amount) if preservation_amount is not None else None,
            cause_of_action=getattr(obj, "cause_of_action", None),
            current_stage=getattr(obj, "current_stage", None),
            current_stage_label=(
                obj.get_current_stage_display()
                if hasattr(obj, "get_current_stage_display") and getattr(obj, "current_stage", None)
                else None
            ),
        )

    @classmethod
    def from_dto(cls, dto: Any) -> CaseOut:
        target_amount = getattr(dto, "target_amount", None)
        return cls(
            id=dto.id,
            name=getattr(dto, "name", ""),
            status=getattr(dto, "status", None),
            status_label=None,
            case_type=getattr(dto, "case_type", None),
            start_date=getattr(dto, "start_date", None),
            effective_date=getattr(dto, "effective_date", None),
            target_amount=float(target_amount) if target_amount is not None else None,
            preservation_amount=None,
            cause_of_action=getattr(dto, "cause_of_action", None),
            current_stage=getattr(dto, "current_stage", None),
            current_stage_label=None,
        )
