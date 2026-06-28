"""API schemas and serializers."""

from __future__ import annotations

from typing import Any, ClassVar

from .assignment_schemas import CaseAssignmentCreate, CaseAssignmentOut
from .base import Case, CaseAssignment, CaseChat, CaseLog, CaseParty, ModelSchema, Schema
from .log_schemas import CaseLogCreate, CaseLogOut
from .number_schemas import CaseNumberIn, CaseNumberOut
from .party_schemas import CasePartyCreate, CasePartyOut
from .supervising_authority_schemas import SupervisingAuthorityIn, SupervisingAuthorityOut

try:
    from apps.contacts.schemas import CaseContactOut
except ImportError:
    CaseContactOut = None  # type: ignore[assignment,misc]


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
            "specified_date",
        ]


class CaseChatOut(ModelSchema):
    class Meta:
        model = CaseChat
        fields: ClassVar = ["id", "platform", "name", "is_active"]


class CaseOut(ModelSchema):
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]
    chats: list[CaseChatOut]
    contract_id: int | None
    contacts: list[CaseContactOut] = []

    class Meta:
        model = Case
        fields: ClassVar = [
            "id",
            "name",
            "status",
            "is_filed",
            "filing_number",
            "case_type",
            "start_date",
            "effective_date",
            "specified_date",
            "target_amount",
            "preservation_amount",
            "cause_of_action",
            "current_stage",
        ]

    @staticmethod
    def _resolve_list_field(obj: Any, key: str) -> list:
        """Common helper: return list data whether obj is a Django model or dict."""
        if isinstance(obj, dict):
            return obj.get(key, [])  # type: ignore[no-any-return]
        return list(getattr(obj, key).all())

    @staticmethod
    def resolve_parties(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "parties")

    @staticmethod
    def resolve_assignments(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "assignments")

    @staticmethod
    def resolve_logs(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "logs")

    @staticmethod
    def resolve_status(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("status")
        return obj.get_status_display() if obj.status else None

    @staticmethod
    def resolve_current_stage(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("current_stage")
        return obj.get_current_stage_display() if obj.current_stage else None

    @staticmethod
    def resolve_contract_id(obj: Any) -> int | None:
        if isinstance(obj, dict):
            return obj.get("contract_id")
        return obj.contract_id  # type: ignore[no-any-return]

    @staticmethod
    def resolve_case_numbers(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "case_numbers")

    @staticmethod
    def resolve_supervising_authorities(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "supervising_authorities")

    @staticmethod
    def resolve_chats(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "chats")

    @staticmethod
    def resolve_contacts(obj: Any) -> list:
        if CaseContactOut is None:
            return []
        return CaseOut._resolve_list_field(obj, "contacts")


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
    "CaseChatOut",
    "CaseCreateFull",
    "CaseFullOut",
    "CaseIn",
    "CaseOut",
    "CaseUpdate",
    "LegalStatusItem",
    "UnifiedGenerateRequest",
]
