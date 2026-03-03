"""Business logic services."""

from __future__ import annotations

from apps.contracts.models import Contract, ContractAssignment


class ContractAssignmentQueryService:
    def list_lawyer_ids_by_contract_internal(self, contract_id: int) -> list[int]:
        if not Contract.objects.filter(id=contract_id).exists():
            return []

        return list(
            ContractAssignment.objects.filter(contract_id=contract_id)
            .order_by("-is_primary", "order", "id")
            .values_list("lawyer_id", flat=True)
        )

    def get_primary_lawyer(self, contract_id: int) -> ContractAssignment | None:
        """获取合同的主办律师指派记录。"""
        return (
            ContractAssignment.objects.filter(contract_id=contract_id, is_primary=True).select_related("lawyer").first()
        )

    def get_all_lawyers(self, contract_id: int) -> list[ContractAssignment]:
        """获取合同的所有律师指派记录（按 is_primary 降序、order 升序）。"""
        return list(
            ContractAssignment.objects.filter(contract_id=contract_id)
            .select_related("lawyer")
            .order_by("-is_primary", "order", "id")
        )
