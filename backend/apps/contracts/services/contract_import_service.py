"""合同 JSON 导入服务（级联创建 Client 和 Lawyer）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.client.services.client_resolve_service import ClientResolveService
    from apps.contracts.models import Contract
    from apps.organization.services.lawyer_resolve_service import LawyerResolveService

logger = logging.getLogger("apps.contracts")

_CONTRACT_FIELDS: tuple[str, ...] = (
    "name",
    "case_type",
    "status",
    "specified_date",
    "start_date",
    "end_date",
    "is_archived",
    "fee_mode",
    "fixed_amount",
    "risk_rate",
    "custom_terms",
    "representation_stages",
    "filing_number",
)


class ContractImportService:
    """按 filing_number get_or_create Contract，级联创建 Client 和 Lawyer。"""

    def __init__(
        self,
        client_resolve: ClientResolveService,
        lawyer_resolve: LawyerResolveService,
    ) -> None:
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve

    @transaction.atomic
    def resolve(self, data: dict[str, Any]) -> Contract:
        from apps.contracts.models import Contract, ContractAssignment, ContractParty

        if not data.get("name"):
            raise ValidationException(message=_("合同名称不能为空"), code="INVALID_CONTRACT_DATA")

        filing_number: str | None = data.get("filing_number") or None
        if filing_number:
            existing = Contract.objects.filter(filing_number=filing_number).first()
            if existing:
                logger.info("复用已有合同", extra={"contract_id": existing.pk, "filing_number": filing_number})
                return existing

        contract_data = {f: data[f] for f in _CONTRACT_FIELDS if f in data}
        contract = Contract.objects.create(**contract_data)
        logger.info("创建新合同", extra={"contract_id": contract.pk, "name": contract.name})

        for party_data in data.get("parties") or []:
            client_data = party_data.get("client")
            if not client_data:
                continue
            client = self._client_resolve.resolve(client_data)
            role = party_data.get("role", "PRINCIPAL")
            ContractParty.objects.get_or_create(contract=contract, client=client, defaults={"role": role})

        for assign_data in data.get("assignments") or []:
            lawyer_data = assign_data.get("lawyer")
            if not lawyer_data:
                continue
            lawyer = self._lawyer_resolve.resolve(lawyer_data)
            if lawyer is None:
                continue
            ContractAssignment.objects.get_or_create(
                contract=contract,
                lawyer=lawyer,
                defaults={
                    "is_primary": assign_data.get("is_primary", False),
                    "order": assign_data.get("order", 0),
                },
            )

        return contract
