"""当事人查询门面（含权限检查）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

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
        page: int = 1,
        page_size: int = 20,
        max_page_size: int = 100,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: User | None = None,
    ) -> QuerySet[Client, Client]:
        if user is not None:
            self.access_policy.ensure_has_perm(user, "client.view_client", "无权限查看客户")
        return self.query_service.list_clients(
            page=page,
            page_size=page_size,
            max_page_size=max_page_size,
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
