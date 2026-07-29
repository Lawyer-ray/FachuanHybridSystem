"""Business logic services."""

from __future__ import annotations

from typing import Any


def _serialize_parties(case: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": party.id,
            "client_id": party.client.id,
            "client_name": party.client.name,
            "legal_status": party.legal_status,
        }
        for party in case.parties.all()
    ]


def _serialize_authorities(case: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": authority.id,
            "name": authority.name,
            "authority_type": authority.authority_type,
        }
        for authority in case.supervising_authorities.all()
    ]


class ContractDetailsAssembler:
    def to_dict(self, contract: Any) -> dict[str, Any]:
        contract_parties = []
        for party in contract.contract_parties.all():
            client = party.client
            contract_parties.append(
                {
                    "id": party.id,
                    "client_id": client.id,
                    "client_name": client.name,
                    "client_type": client.client_type if hasattr(client, "client_type") else None,
                    "id_number": getattr(client, "id_number", None),
                    "legal_representative": getattr(client, "legal_representative", None),
                    "address": getattr(client, "address", None),
                    "phone": getattr(client, "phone", None),
                    "role": party.role,
                }
            )

        assignments = []
        for assignment in contract.assignments.all():
            lawyer = assignment.lawyer
            assignments.append(
                {
                    "id": assignment.id,
                    "lawyer_id": lawyer.id,
                    "lawyer_name": lawyer.real_name if hasattr(lawyer, "real_name") else str(lawyer),
                    "lawyer_phone": getattr(lawyer, "phone", None),
                    "lawyer_license_no": getattr(lawyer, "license_no", None),
                    "is_primary": assignment.is_primary,
                    "order": assignment.order,
                    "law_firm_name": lawyer.law_firm.name if hasattr(lawyer, "law_firm") and lawyer.law_firm else None,
                }
            )

        cases = []
        for case in contract.cases.all():
            cases.append(
                {
                    "id": case.id,
                    "name": case.name,
                    "cause_of_action": case.cause_of_action,
                    "target_amount": float(case.target_amount) if case.target_amount else None,
                    "parties": _serialize_parties(case),
                    "supervising_authorities": _serialize_authorities(case),
                }
            )

        return {
            "id": contract.id,
            "name": contract.name,
            "case_type": contract.case_type,
            "status": contract.status,
            "fee_mode": contract.fee_mode,
            "fixed_amount": contract.fixed_amount,
            "risk_rate": contract.risk_rate,
            "custom_terms": contract.custom_terms,
            "representation_stages": contract.representation_stages or [],
            "specified_date": str(contract.specified_date) if contract.specified_date else None,
            "start_date": str(contract.start_date) if contract.start_date else None,
            "end_date": str(contract.end_date) if contract.end_date else None,
            "is_filed": contract.is_filed,
            "contract_parties": contract_parties,
            "assignments": assignments,
            "cases": cases,
        }
