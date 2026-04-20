"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import QuerySet

from apps.contracts.models import Contract

if TYPE_CHECKING:
    from apps.core.security import AccessContext


class ContractServiceQueryMixin:
    query_service: Any
    query_facade: Any

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        return cast(QuerySet[Contract, Contract], self.query_service.get_contract_queryset())

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
        return cast(
            dict[str, Any],
            self.query_facade.list_contracts(
                case_type=case_type,
                status=status,
                is_filed=is_filed,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                page=page,
                page_size=page_size,
            ),
        )

    def _get_contract_internal(self, contract_id: int) -> Any:
        return self.query_service.get_contract_internal(contract_id)

    def get_contract(
        self,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        return cast(
            Contract,
            self.query_facade.get_contract(
                contract_id=contract_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def get_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Any:
        return self.query_facade.get_contract_ctx(contract_id=contract_id, ctx=ctx)
