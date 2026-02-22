"""Business logic services."""

from __future__ import annotations

from typing import Any, ClassVar

from apps.contracts.models import Contract
from apps.core.enums import CaseType
from apps.core.exceptions import NotFoundError

from .wiring import get_case_service


class ContractAdminQueryService:
    CASE_ALLOWED_TYPES: ClassVar = {
        CaseType.CIVIL,
        CaseType.CRIMINAL,
        CaseType.ADMINISTRATIVE,
        CaseType.LABOR,
        CaseType.INTL,
    }

    def can_create_case(self, contract_id: int) -> bool:
        contract = Contract.objects.filter(pk=contract_id).only("id", "case_type").first()
        if not contract:
            return False
        return contract.case_type in self.CASE_ALLOWED_TYPES

    def get_contract_detail(self, contract_id: int) -> Any:
        try:
            return (
                Contract.objects.select_related("folder_binding")
                .prefetch_related(
                    "contract_parties__client",
                    "assignments__lawyer",
                    "payments",
                    "reminders",
                    "supplementary_agreements__parties__client",
                )
                .get(pk=contract_id)
            )
        except Contract.DoesNotExist as exc:
            raise NotFoundError(f"合同 {contract_id} 不存在") from exc

    def get_related_cases(self, contract_id: int) -> list[dict[str, Any]]:
        case_service = get_case_service()
        cases_dto = case_service.get_cases_by_contract(contract_id)
        if not cases_dto:
            return []

        case_ids = [case.id for case in cases_dto]
        case_primary_lawyer_map = case_service.get_primary_lawyer_names_by_case_ids_internal(case_ids)

        from apps.core.enums import CaseStatus

        status_map = dict(CaseStatus.choices)
        return [
            {
                "id": case.id,
                "name": case.name,
                "status": case.status,
                "status_display": status_map.get(case.status, case.status),
                "cause_of_action": case.cause_of_action or "未设置",
                "primary_lawyer": case_primary_lawyer_map.get(case.id) or "未指派",
                "detail_url": f"/admin/cases/case/{case.id}/detail/",
            }
            for case in cases_dto
        ]
