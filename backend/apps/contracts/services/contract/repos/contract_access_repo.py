"""Data repository layer."""


from __future__ import annotations

from collections.abc import Iterable

from apps.contracts.models import Contract, ContractAssignment


class ContractAccessRepo:
    def has_assignment_access(self, *, contract_id: int, lawyer_ids: Iterable[int]) -> bool:
        lawyer_ids_list = list(lawyer_ids)
        if not lawyer_ids_list:
            return False
        return ContractAssignment.objects.filter(contract_id=contract_id, lawyer_id__in=lawyer_ids_list).exists()

    def has_case_assignment_access(self, *, contract_id: int, user_id: int) -> bool:
        return Contract.objects.filter(id=contract_id, cases__assignments__lawyer_id=user_id).exists()
