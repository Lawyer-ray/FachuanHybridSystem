"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract
from apps.core.exceptions import NotFoundError
from apps.core.security.access_context import AccessContext

from ..domain import ContractAccessPolicy


class ContractQueryService:
    def __init__(self, access_policy: ContractAccessPolicy | None = None) -> None:
        self._access_policy = access_policy

    @property
    def access_policy(self) -> ContractAccessPolicy:
        if self._access_policy is None:
            self._access_policy = ContractAccessPolicy()
        return self._access_policy

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        return Contract.objects.prefetch_related(
            "cases",
            "contract_parties__client",
            "payments",
            "reminders",
            "assignments__lawyer",
            "assignments__lawyer__law_firm",
            "supplementary_agreements__parties__client",
        )

    def _apply_list_filters(
        self,
        qs: QuerySet[Contract, Contract],
        *,
        case_type: str | None,
        status: str | None,
        is_archived: bool | None,
    ) -> QuerySet[Contract, Contract]:
        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if is_archived is not None:
            qs = qs.filter(is_archived=is_archived)
        return qs

    def list_contracts(
        self,
        case_type: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Contract, Contract]:
        qs = self.get_contract_queryset().order_by("-id")
        qs = self._apply_list_filters(qs, case_type=case_type, status=status, is_archived=is_archived)

        qs = self.access_policy.filter_queryset(
            qs=qs,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return qs

    def list_contracts_ctx(
        self,
        *,
        ctx: AccessContext,
        case_type: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
    ) -> QuerySet[Contract, Contract]:
        qs = self.get_contract_queryset().order_by("-id")
        qs = self._apply_list_filters(qs, case_type=case_type, status=status, is_archived=is_archived)

        qs = self.access_policy.filter_queryset_ctx(qs=qs, ctx=ctx)
        return qs

    def get_contract_internal(self, contract_id: int) -> Any:
        try:
            contract = self.get_contract_queryset().get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(_("合同 %(id)s 不存在") % {"id": contract_id}) from None
        return contract

    def get_contract_with_details_model_internal(self, contract_id: int) -> Any:
        try:
            return Contract.objects.prefetch_related(
                "contract_parties__client",
                "assignments__lawyer",
                "assignments__lawyer__law_firm",
                "cases__parties__client",
                "cases__supervising_authorities",
            ).get(pk=contract_id)
        except Contract.DoesNotExist:
            return None
