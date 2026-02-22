"""当事人查询服务组合。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
    from django.db.models import QuerySet

    from apps.client.models import Client

    from .query import ClientBatchQueryService, ClientGetQueryService, ClientListQueryService


class ClientQueryService:
    def __init__(
        self,
        list_query: ClientListQueryService | None = None,
        get_query: ClientGetQueryService | None = None,
        batch_query: ClientBatchQueryService | None = None,
    ) -> None:
        self._list_query = list_query
        self._get_query = get_query
        self._batch_query = batch_query

    @property
    def list_query(self) -> ClientListQueryService:
        if self._list_query is None:
            from .query import ClientListQueryService

            self._list_query = ClientListQueryService()
        return self._list_query

    @property
    def get_query(self) -> ClientGetQueryService:
        if self._get_query is None:
            from .query import ClientGetQueryService

            self._get_query = ClientGetQueryService()
        return self._get_query

    @property
    def batch_query(self) -> ClientBatchQueryService:
        if self._batch_query is None:
            from .query import ClientBatchQueryService

            self._batch_query = ClientBatchQueryService()
        return self._batch_query

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
        return self.list_query.list_clients(
            page=page,
            page_size=page_size,
            max_page_size=max_page_size,
            client_type=client_type,
            is_our_client=is_our_client,
            search=search,
            user=user,
        )

    def get_client(self, *, client_id: int, user: User | None = None) -> Client:
        return self.get_query.get_client(client_id=client_id, user=user)

    def get_clients_by_ids(self, *, client_ids: list[int]) -> list[Client]:
        return self.batch_query.get_clients_by_ids(client_ids=client_ids)
