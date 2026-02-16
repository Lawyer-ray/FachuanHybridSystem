"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from apps.contracts.models import Contract

if TYPE_CHECKING:
    from apps.core.security import AccessContext


class ContractServiceQueryMixin:
    query_service: Any
    query_facade: Any

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        return self.query_service.get_contract_queryset()  # type: ignore[no-any-return]

    def list_contracts(
        self,
        case_type: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[Contract]:
        return self.query_facade.list_contracts(  # type: ignore[no-any-return]
            case_type=case_type,
            status=status,
            is_archived=is_archived,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
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
        return self.query_facade.get_contract(  # type: ignore[no-any-return]
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def get_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Any:
        return self.query_facade.get_contract_ctx(contract_id=contract_id, ctx=ctx)
