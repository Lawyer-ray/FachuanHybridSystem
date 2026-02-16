"""Business logic services."""

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
