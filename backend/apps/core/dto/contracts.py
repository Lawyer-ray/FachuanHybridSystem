"""Module for contracts."""

from dataclasses import dataclass
from typing import Any


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
    def from_model(cls, contract: Any) -> "ContractDTO":
        primary_lawyer = contract.primary_lawyer if hasattr(contract, "primary_lawyer") else None

        return cls(
            id=contract.id,
            name=contract.name,
            case_type=contract.case_type,
            status=contract.status,
            representation_stages=contract.representation_stages or [],
            primary_lawyer_id=primary_lawyer.id if primary_lawyer else None,
            primary_lawyer_name=(
                primary_lawyer.real_name if primary_lawyer and hasattr(primary_lawyer, "real_name") else None
            ),
            fee_mode=contract.fee_mode if hasattr(contract, "fee_mode") else None,
            fixed_amount=contract.fixed_amount if hasattr(contract, "fixed_amount") else None,
            risk_rate=contract.risk_rate if hasattr(contract, "risk_rate") else None,
            is_archived=contract.is_archived if hasattr(contract, "is_archived") else False,
            start_date=str(contract.start_date) if hasattr(contract, "start_date") and contract.start_date else None,
            end_date=str(contract.end_date) if hasattr(contract, "end_date") and contract.end_date else None,
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
    def from_model(cls, agreement: Any) -> "SupplementaryAgreementDTO":
        return cls(
            id=agreement.id,
            contract_id=agreement.contract_id,
            title=agreement.title,
            content=agreement.content if hasattr(agreement, "content") else None,
            signed_date=str(agreement.signed_date) if agreement.signed_date else None,
            file_path=agreement.file.url if hasattr(agreement, "file") and agreement.file else None,
            created_at=str(agreement.created_at) if agreement.created_at else None,
        )
