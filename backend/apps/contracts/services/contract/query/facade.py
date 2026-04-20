"""Business logic services."""

from __future__ import annotations

import math
from typing import Any

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract
from apps.core.security.access_context import AccessContext

from ..assemblers.contract_list_assembler import ContractListAssembler
from ..domain import ContractAccessPolicy
from .service import ContractQueryService


class ContractQueryFacade:
    def __init__(
        self,
        query_service: ContractQueryService | None = None,
        access_policy: ContractAccessPolicy | None = None,
        list_assembler: ContractListAssembler | None = None,
    ) -> None:
        self._query_service = query_service
        self._access_policy = access_policy
        self._list_assembler = list_assembler

    @property
    def query_service(self) -> ContractQueryService:
        if self._query_service is None:
            self._query_service = ContractQueryService(access_policy=self.access_policy)
        return self._query_service

    @property
    def access_policy(self) -> ContractAccessPolicy:
        if self._access_policy is None:
            self._access_policy = ContractAccessPolicy()
        return self._access_policy

    @property
    def list_assembler(self) -> ContractListAssembler:
        if self._list_assembler is None:
            self._list_assembler = ContractListAssembler()
        return self._list_assembler

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        return self.query_service.get_contract_queryset()

    def list_contracts(
        self,
        case_type: str | None = None,
        status: str | None = None,
        is_filed: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        qs = self.query_service.list_contracts(
            case_type=case_type,
            status=status,
            is_filed=is_filed,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        total = qs.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        start = (page - 1) * page_size
        contracts = list(qs[start : start + page_size])
        self.list_assembler.enrich(contracts)
        return {
            "items": contracts,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def list_contracts_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        is_filed: bool | None = None,
    ) -> list[Contract]:
        qs = self.query_service.list_contracts_ctx(
            ctx=ctx,
            case_type=case_type,
            status=status,
            is_filed=is_filed,
        )
        contracts = list(qs)
        self.list_assembler.enrich(contracts)
        return contracts

    def get_contract(
        self,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        contract = self.query_service.get_contract_internal(contract_id)
        self.access_policy.ensure_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            contract=contract,
            message=_("无权限访问该合同"),
        )
        self.list_assembler.enrich([contract])
        return contract  # type: ignore[no-any-return]

    def get_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Any:
        contract = self.query_service.get_contract_internal(contract_id)
        self.access_policy.ensure_access_ctx(
            contract_id=contract_id, ctx=ctx, contract=contract, message=_("无权限访问该合同")
        )
        self.list_assembler.enrich([contract])
        return contract
