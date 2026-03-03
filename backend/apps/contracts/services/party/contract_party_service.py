"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractParty
from apps.core.exceptions import NotFoundError


class ContractPartyService:
    def add_party(self, contract_id: int, client_id: int) -> ContractParty:
        if not Contract.objects.filter(id=contract_id).exists():
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id})

        party, _ = ContractParty.objects.get_or_create(contract_id=contract_id, client_id=client_id)
        return party

    def remove_party(self, contract_id: int, client_id: int) -> None:
        deleted, _ = ContractParty.objects.filter(contract_id=contract_id, client_id=client_id).delete()
        if not deleted:
            raise NotFoundError(
                _("合同 %(cid)s 中不存在客户 %(pid)s 的当事人记录") % {"cid": contract_id, "pid": client_id}
            )

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        contract = Contract.objects.filter(id=contract_id).prefetch_related("contract_parties__client").first()
        if not contract:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id})

        parties = []
        for party in contract.contract_parties.all():
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
