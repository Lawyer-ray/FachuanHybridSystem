"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from apps.cases.models import Case, CaseAssignment


class CaseDetailsQueryService:
    def get_case_model_internal(self, case_id: int) -> Any | None:
        try:
            return Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            return None

    def get_case_with_details_internal(self, case_id: int) -> dict[str, Any] | None:
        try:
            case = (
                Case.objects.prefetch_related(
                    "parties__client",
                    "case_numbers",
                    Prefetch(
                        "assignments",
                        queryset=CaseAssignment.objects.select_related("lawyer__law_firm"),
                    ),
                    "supervising_authorities",
                )
                .select_related("contract")
                .get(pk=case_id)
            )
        except Case.DoesNotExist:
            return None

        case_parties = []
        for party in case.parties.all():
            client = party.client
            case_parties.append(
                {
                    "id": party.id,
                    "client_id": client.id,
                    "client_name": client.name,
                    "client_type": client.client_type if hasattr(client, "client_type") else None,
                    "id_number": getattr(client, "id_number", None),
                    "legal_representative": getattr(client, "legal_representative", None),
                    "address": getattr(client, "address", None),
                    "phone": getattr(client, "phone", None),
                    "legal_status": party.legal_status,
                    "is_our_client": client.is_our_client if hasattr(client, "is_our_client") else False,
                }
            )

        case_numbers = []
        for case_number in case.case_numbers.all():
            case_numbers.append(
                {
                    "id": case_number.id,
                    "number": case_number.number,
                    "document_name": case_number.document_name,
                    "document_content": case_number.document_content,
                    "is_active": case_number.is_active,
                    "remarks": case_number.remarks,
                    "created_at": str(case_number.created_at) if case_number.created_at else None,
                }
            )

        assignments = []
        for assignment in case.assignments.all():
            lawyer = assignment.lawyer
            assignments.append(
                {
                    "id": assignment.id,
                    "lawyer_id": lawyer.id if lawyer else None,
                    "lawyer_name": (
                        lawyer.real_name if lawyer and hasattr(lawyer, "real_name") else str(lawyer) if lawyer else None
                    ),
                    "law_firm_name": (lawyer.law_firm.name if (lawyer and getattr(lawyer, "law_firm", None) and lawyer.law_firm) else None),
                }
            )

        supervising_authorities = []
        for authority in case.supervising_authorities.all():
            supervising_authorities.append(
                {
                    "id": authority.id,
                    "name": authority.name,
                    "authority_type": getattr(authority, "authority_type", None),
                }
            )

        return {
            "id": case.id,
            "name": case.name,
            "case_type": case.case_type,
            "status": case.status,
            "current_stage": case.current_stage,
            "cause_of_action": case.cause_of_action,
            "target_amount": float(case.target_amount) if case.target_amount is not None else None,
            "preservation_amount": (
                float(case.preservation_amount) if case.preservation_amount is not None else None
            ),
            "is_filed": case.is_filed,
            "start_date": str(case.start_date) if getattr(case, "start_date", None) else None,
            "effective_date": str(case.effective_date) if getattr(case, "effective_date", None) else None,
            "specified_date": str(case.specified_date) if getattr(case, "specified_date", None) else None,
            "contract_id": case.contract_id,
            "contract_name": case.contract.name if getattr(case, "contract", None) and case.contract else None,
            "case_parties": case_parties,
            "case_numbers": case_numbers,
            "assignments": assignments,
            "supervising_authorities": supervising_authorities,
        }
