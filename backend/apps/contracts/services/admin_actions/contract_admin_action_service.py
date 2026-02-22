"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from apps.core.protocols import ICaseAssignmentService, ICaseService

logger = logging.getLogger("apps.contracts")


class ContractAdminActionService:
    def __init__(self, *, case_service: ICaseService, case_assignment_service: ICaseAssignmentService) -> None:
        self._case_service = case_service
        self._case_assignment_service = case_assignment_service

    def unbind_cases_from_contract(self, contract_id: int) -> int:
        return int(self._case_service.unbind_cases_from_contract_internal(contract_id))

    def unbind_cases_from_contracts(self, contract_ids: list[int]) -> int:
        total = 0
        for contract_id in contract_ids:
            total += self.unbind_cases_from_contract(contract_id)
        return total

    def sync_case_assignments_from_contract(self, contract_id: int, user: Any | None = None) -> None:
        cases = self._case_service.get_cases_by_contract(contract_id)
        for c in cases:
            self._case_assignment_service.sync_assignments_from_contract(case_id=c.id, user=user, perm_open_access=True)
