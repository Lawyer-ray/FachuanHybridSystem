"""合同当事人操作"""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.models import Contract, ContractParty
from apps.core.exceptions import NotFoundError

from ._base import ContractServiceBase

logger = logging.getLogger("apps.contracts")

__all__ = ["ContractPartiesMixin"]


class ContractPartiesMixin(ContractServiceBase):
    """合同当事人 Mixin"""

    def add_party(self, contract_id: int, client_id: int) -> ContractParty:
        """添加合同当事人"""
        if not Contract.objects.filter(id=contract_id).exists():
            raise NotFoundError(f"合同 {contract_id} 不存在")

        party, _ = ContractParty.objects.get_or_create(
            contract_id=contract_id,
            client_id=client_id,
        )

        return party

    def remove_party(self, contract_id: int, client_id: int) -> None:
        """移除合同当事人"""
        deleted, _ = ContractParty.objects.filter(
            contract_id=contract_id,
            client_id=client_id,
        ).delete()

        if not deleted:
            raise NotFoundError(f"合同 {contract_id} 中不存在客户 {client_id} 的当事人记录")

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        """
        获取合同及其补充协议的所有当事人

        Requirements: 2.1, 2.2, 2.3, 2.4
        """
        contract = self._get_contract_internal(contract_id)

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
