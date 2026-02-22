"""Module for contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.contracts.models import Contract, SupplementaryAgreement


@dataclass
class ContractDTO:
    id: int
    name: str
    case_type: str
    status: str
    representation_stages: list[str]
    primary_lawyer_id: int | None = None
    primary_lawyer_name: str | None = None
    fee_mode: str | None = None
    fixed_amount: Any | None = None
    risk_rate: Any | None = None
    is_archived: bool = False
    start_date: str | None = None
    end_date: str | None = None

    @classmethod
    def from_model(cls, contract: Contract) -> ContractDTO:
        primary_lawyer = contract.primary_lawyer  # type: ignore[attr-defined]

        stages = contract.representation_stages
        representation_stages: list[str] = stages if isinstance(stages, list) else []

        return cls(
            id=contract.id,
            name=contract.name,
            case_type=contract.case_type,
            status=contract.status,
            representation_stages=representation_stages,
            primary_lawyer_id=primary_lawyer.id if primary_lawyer else None,
            primary_lawyer_name=primary_lawyer.real_name if primary_lawyer else None,
            fee_mode=contract.fee_mode,
            fixed_amount=contract.fixed_amount,
            risk_rate=contract.risk_rate,
            is_archived=contract.is_archived,
            start_date=str(contract.start_date) if contract.start_date else None,
            end_date=str(contract.end_date) if contract.end_date else None,
        )


@dataclass
class PartyRoleDTO:
    id: int
    contract_id: int
    client_id: int
    client_name: str
    role_type: str
    is_our_client: bool = False


@dataclass
class SupplementaryAgreementDTO:
    id: int
    contract_id: int
    title: str
    content: str | None = None
    signed_date: str | None = None
    file_path: str | None = None
    created_at: str | None = None

    @classmethod
    def from_model(cls, agreement: SupplementaryAgreement) -> SupplementaryAgreementDTO:
        return cls(
            id=agreement.id,
            contract_id=agreement.contract_id,
            title=agreement.name or "",
            content=None,
            signed_date=None,
            file_path=None,
            created_at=str(agreement.created_at) if agreement.created_at else None,
        )
