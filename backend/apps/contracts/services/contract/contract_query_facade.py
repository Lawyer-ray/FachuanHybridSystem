"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from typing import Any, cast

from django.db.models import QuerySet

from apps.contracts.models import Contract
from apps.core.security.access_context import AccessContext

from .assemblers.contract_list_assembler import ContractListAssembler
from .contract_access_policy import ContractAccessPolicy
from .contract_query_service import ContractQueryService


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
        is_archived: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[Contract]:
        qs = self.query_service.list_contracts(
            case_type=case_type,
            status=status,
            is_archived=is_archived,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        contracts = list(qs)
        self.list_assembler.enrich(contracts)
        return contracts

    def list_contracts_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
    ) -> list[Contract]:
        qs = self.query_service.list_contracts_ctx(
            ctx=ctx,
            case_type=case_type,
            status=status,
            is_archived=is_archived,
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
        return cast(Contract, contract)

    def get_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Any:
        contract = self.query_service.get_contract_internal(contract_id)
        self.access_policy.ensure_access_ctx(
            contract_id=contract_id, ctx=ctx, contract=contract, message=_("无权限访问该合同")
        )
        self.list_assembler.enrich([contract])
        return contract
