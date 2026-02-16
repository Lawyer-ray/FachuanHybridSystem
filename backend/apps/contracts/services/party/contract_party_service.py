"""Business logic services."""

from typing import Any

from apps.contracts.models import Contract, ContractParty
from apps.core.exceptions import NotFoundError


class ContractPartyService:
    def add_party(self, contract_id: int, client_id: int) -> ContractParty:
        if not Contract.objects.filter(id=contract_id).exists():
            raise NotFoundError(f"合同 {contract_id} 不存在")

        party, _ = ContractParty.objects.get_or_create(contract_id=contract_id, client_id=client_id)
        return party

    def remove_party(self, contract_id: int, client_id: int) -> bool:
        deleted, _ = ContractParty.objects.filter(contract_id=contract_id, client_id=client_id).delete()
        return deleted > 0

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        contract = Contract.objects.filter(id=contract_id).prefetch_related("parties__client").first()
        if not contract:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        parties = []
        for party in contract.parties.all():
            client = party.client
            parties.append(
                {
                    "id": party.id,
                    "client_id": party.client_id,
                    "client_name": getattr(client, "name", "") if client else "",
                    "client_type": getattr(client, "client_type", None) if client else None,
                }
            )
        return parties
