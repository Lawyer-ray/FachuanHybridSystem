"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from typing import Any

from apps.core.exceptions import NotFoundError


class GetContractAllPartiesUseCase:
    def __init__(self, contract_query_service: Any) -> None:
        self.contract_query_service = contract_query_service

    def execute(self, contract_id: int) -> list[dict[str, Any]]:
        contract = self.contract_query_service.get_contract_internal(contract_id)
        if not contract:
            raise NotFoundError(message=_("合同不存在"), code="CONTRACT_NOT_FOUND", errors={"contract_id": contract_id})

        parties_dict: dict[int, dict[str, Any]] = {}

        for party in contract.contract_parties.select_related("client").all():
            client = party.client
            if client.id not in parties_dict:
                parties_dict[client.id] = {
                    "id": client.id,
                    "name": client.name,
                    "source": "contract",
                    "role": party.role,
                }

        for sa in contract.supplementary_agreements.prefetch_related("parties__client").all():
            for sa_party in sa.parties.all():
                client = sa_party.client
                if client.id not in parties_dict:
                    parties_dict[client.id] = {
                        "id": client.id,
                        "name": client.name,
                        "source": "supplementary",
                        "role": sa_party.role,
                    }

        return list(parties_dict.values())
