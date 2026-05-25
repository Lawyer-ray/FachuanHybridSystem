"""当事人查询门面（含权限检查）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from .client_access_policy import ClientAccessPolicy
from .client_query_service import ClientQueryService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User

    from apps.client.models import Client


class ClientQueryFacade:
    def __init__(
        self,
        query_service: ClientQueryService | None = None,
        access_policy: ClientAccessPolicy | None = None,
    ) -> None:
        self._query_service = query_service
        self._access_policy = access_policy

    @property
    def query_service(self) -> ClientQueryService:
        if self._query_service is None:
            self._query_service = ClientQueryService()
        return self._query_service

    @property
    def access_policy(self) -> ClientAccessPolicy:
        if self._access_policy is None:
            self._access_policy = ClientAccessPolicy()
        return self._access_policy

    def list_clients(
        self,
        *,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: User | None = None,
    ) -> QuerySet[Client, Client]:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", _("无权限查看客户"))
        return self.query_service.list_clients(
            client_type=client_type,
            is_our_client=is_our_client,
            search=search,
            user=user,
        )

    def get_client(self, *, client_id: int, user: User | None = None) -> Client:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", _("无权限查看客户"))
        return self.query_service.get_client(client_id=client_id, user=user)

    def get_clients_by_ids(self, *, client_ids: list[int], user: User | None = None) -> list[Client]:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", _("无权限查看客户"))
        return self.query_service.get_clients_by_ids(client_ids=client_ids)

    def get_related_items(self, *, client_id: int) -> dict[str, list[dict[str, Any]]]:
        """获取客户关联的案件和合同。"""
        from apps.cases.models import CaseParty
        from apps.contracts.models import ContractParty

        case_parties = (
            CaseParty.objects.filter(client_id=client_id).select_related("case").order_by("-case__start_date")
        )
        contract_parties = (
            ContractParty.objects.filter(client_id=client_id)
            .select_related("contract")
            .order_by("-contract__specified_date")
        )

        cases = [
            {
                "id": cp.case.id,
                "name": cp.case.name,
                "case_type": cp.case.case_type,
                "status": cp.case.get_status_display() if cp.case.status else None,
                "current_stage": cp.case.get_current_stage_display() if cp.case.current_stage else None,
                "legal_status": cp.legal_status,
            }
            for cp in case_parties
        ]
        contracts = [
            {
                "id": cp.contract.id,
                "name": cp.contract.name,
                "case_type": cp.contract.case_type,
                "status": cp.contract.get_status_display() if cp.contract.status else None,
                "role": cp.role,
            }
            for cp in contract_parties
        ]

        return {"cases": cases, "contracts": contracts}
