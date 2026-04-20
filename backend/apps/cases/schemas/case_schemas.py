"""API schemas and serializers."""

from __future__ import annotations

from typing import ClassVar

from .assignment_schemas import CaseAssignmentCreate, CaseAssignmentOut
from .base import Case, CaseAssignment, CaseLog, CaseParty, ModelSchema, Schema
from .log_schemas import CaseLogCreate, CaseLogOut
from .number_schemas import CaseNumberIn, CaseNumberOut
from .party_schemas import CasePartyCreate, CasePartyOut
from .supervising_authority_schemas import SupervisingAuthorityIn, SupervisingAuthorityOut


class CaseIn(ModelSchema):
    class Meta:
        model = Case
        fields: ClassVar = [
            "name",
            "status",
            "is_filed",
            "case_type",
            "target_amount",
            "preservation_amount",
            "cause_of_action",
            "current_stage",
            "effective_date",
        ]


class CaseOut(ModelSchema):
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]
    contract_id: int | None

    class Meta:
        model = Case
        fields: ClassVar = [
            "id",
            "name",
            "status",
            "is_filed",
            "case_type",
            "start_date",
            "effective_date",
            "target_amount",
            "preservation_amount",
            "cause_of_action",
            "current_stage",
        ]

    @staticmethod
    def resolve_parties(obj: Case) -> list[CaseParty]:
        return list(obj.parties.all())

    @staticmethod
    def resolve_assignments(obj: Case) -> list[CaseAssignment]:
        return list(obj.assignments.all())

    @staticmethod
    def resolve_logs(obj: Case) -> list[CaseLog]:
        return list(obj.logs.all())

    @staticmethod
    def resolve_status(obj: Case) -> str | None:
        return obj.get_status_display() if obj.status else None

    @staticmethod
    def resolve_current_stage(obj: Case) -> str | None:
        return obj.get_current_stage_display() if obj.current_stage else None

    @staticmethod
    def resolve_contract_id(obj: Case) -> int | None:
        return obj.contract_id

    @staticmethod
    def resolve_case_numbers(obj: Case) -> list[CaseNumberOut]:
        return list(obj.case_numbers.all())

    @staticmethod
    def resolve_supervising_authorities(obj: Case) -> list[SupervisingAuthorityOut]:
        return list(obj.supervising_authorities.all())


class CaseUpdate(Schema):
    name: str | None = None
    status: str | None = None
    is_filed: bool | None = None
    case_type: str | None = None
    target_amount: float | None = None
    preservation_amount: float | None = None
    cause_of_action: str | None = None
    current_stage: str | None = None
    effective_date: str | None = None


class CaseCreateFull(Schema):
    case: CaseIn
    parties: list[CasePartyCreate] | None = None
    assignments: list[CaseAssignmentCreate] | None = None
    logs: list[CaseLogCreate] | None = None
    case_numbers: list[CaseNumberIn] | None = None
    supervising_authorities: list[SupervisingAuthorityIn] | None = None


class CaseFullOut(Schema):
    case: CaseOut
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]


class LegalStatusItem(Schema):
    value: str
    label: str


class UnifiedGenerateRequest(Schema):
    template_id: int | None = None
    function_code: str | None = None
    client_id: int | None = None
    client_ids: list[int] | None = None
    mode: str | None = None


__all__: list[str] = [
    "CaseCreateFull",
    "CaseFullOut",
    "CaseIn",
    "CaseOut",
    "CaseUpdate",
    "LegalStatusItem",
    "UnifiedGenerateRequest",
]
