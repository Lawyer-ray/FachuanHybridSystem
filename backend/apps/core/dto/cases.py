"""Module for cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.cases.models import Case, CaseParty, CaseTemplateBinding


@dataclass
class CaseDTO:
    id: int
    name: str
    current_stage: str | None = None
    contract_id: int | None = None
    status: str = "active"
    case_type: str | None = None
    cause_of_action: str | None = None
    target_amount: str | None = None
    is_filed: bool = False
    start_date: str | None = None
    effective_date: str | None = None
    case_number: str | None = None

    @classmethod
    def from_model(cls, case: Case) -> CaseDTO:
        return cls(
            id=case.id,
            name=case.name,
            current_stage=case.current_stage,
            contract_id=case.contract_id,
            status=case.status,
            case_type=case.case_type,
            cause_of_action=case.cause_of_action,
            target_amount=str(case.target_amount) if case.target_amount is not None else None,
            is_filed=case.is_filed,
            start_date=str(case.start_date) if case.start_date else None,
            effective_date=str(case.effective_date) if case.effective_date else None,
        )


@dataclass
class CaseSearchResultDTO:
    id: int
    name: str
    case_numbers: list[str] = field(default_factory=list)
    parties: list[str] = field(default_factory=list)
    created_at: str | None = None


@dataclass
class CaseTemplateBindingDTO:
    id: int
    case_id: int
    template_id: int
    template_name: str
    template_function_code: str | None = None
    binding_source: str = "manual"
    created_at: str | None = None

    @classmethod
    def from_model(cls, binding: CaseTemplateBinding) -> CaseTemplateBindingDTO:
        return cls(
            id=binding.id,
            case_id=binding.case_id,
            template_id=binding.template_id,
            template_name=binding.template.name if binding.template else "",
            template_function_code=None,
            binding_source=binding.binding_source,
            created_at=str(binding.created_at) if binding.created_at else None,
        )


@dataclass
class CasePartyDTO:
    id: int
    case_id: int
    client_id: int
    client_name: str
    client_type: str
    legal_status: str
    id_number: str | None = None
    address: str | None = None
    phone: str | None = None
    legal_representative: str | None = None
    is_our_client: bool = False

    @classmethod
    def from_model(cls, party: CaseParty) -> CasePartyDTO:
        client = party.client
        return cls(
            id=party.id,
            case_id=party.case_id,
            client_id=party.client_id,
            client_name=client.name if client else "",
            client_type=client.client_type if client else "natural",
            legal_status=party.legal_status or "",
            id_number=client.id_number if client else None,
            address=client.address if client else None,
            phone=client.phone if client else None,
            legal_representative=client.legal_representative if client else None,
            is_our_client=client.is_our_client if client else False,
        )
