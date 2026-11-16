"""当事人查询门面（含权限检查）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from .client_access_policy import ClientAccessPolicy
from .client_query_service import ClientQueryService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User

    from apps.client.models import Client
    from apps.client.ports import RelatedItemsPort


class ClientQueryFacade:
    def __init__(
        self,
        query_service: ClientQueryService | None = None,
        access_policy: ClientAccessPolicy | None = None,
        related_items_port: RelatedItemsPort | None = None,
    ) -> None:
        self._query_service = query_service
        self._access_policy = access_policy
        self._related_items_port = related_items_port

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

    @property
    def related_items_port(self) -> RelatedItemsPort:
        if self._related_items_port is None:
            from .wiring import get_related_items_port

            self._related_items_port = get_related_items_port()
        return self._related_items_port

    def list_clients(
        self,
        *,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: User | None = None,
    ) -> QuerySet[Client, Client]:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", "无权限查看客户")
        return self.query_service.list_clients(
            client_type=client_type,
            is_our_client=is_our_client,
            search=search,
            user=user,
        )

    def get_client(self, *, client_id: int, user: User | None = None) -> Client:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", "无权限查看客户")
        return self.query_service.get_client(client_id=client_id, user=user)

    def get_clients_by_ids(self, *, client_ids: list[int], user: User | None = None) -> list[Client]:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", "无权限查看客户")
        return self.query_service.get_clients_by_ids(client_ids=client_ids)

    def get_related_items(self, *, client_id: int, user: User | None = None) -> dict[str, list[dict[str, Any]]]:
        """获取客户关联的案件和合同（安全审计：按查询用户过滤越权条目）。

        跨模块（cases/contracts）查询经 RelatedItemsPort 委托适配器，
        本门面只负责客户查看权限校验。
        """
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", "无权限查看客户")
        return self.related_items_port.get_related_items(client_id=client_id, user=user)
