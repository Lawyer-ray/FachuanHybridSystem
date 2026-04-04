"""Business workflow orchestration."""

from __future__ import annotations

from typing import Any

from apps.contracts.models import Contract
from apps.core.interfaces import CaseDTO


class ContractCaseCreationWorkflow:
    def __init__(self, *, case_service: Any) -> None:
        self.case_service = case_service

    def create_case_from_contract(
        self,
        *,
        contract: Contract,
        case_data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        case_dto = self.case_service.create_case(
            case_data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        for party in contract.contract_parties.all():
            self.case_service.create_case_party(
                case_id=case_dto.id,
                client_id=party.client_id,
                legal_status=None,
            )

        for assignment in contract.assignments.all():
            self.case_service.create_case_assignment(
                case_id=case_dto.id,
                lawyer_id=assignment.lawyer_id,
            )

        return case_dto
