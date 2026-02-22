"""当事人批量查询服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.client.services.client_internal_query_service import ClientInternalQueryService

if TYPE_CHECKING:
    from apps.client.models import Client


class ClientBatchQueryService:
    def __init__(self, internal_query_service: ClientInternalQueryService | None = None) -> None:
        self._internal_query_service = internal_query_service

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
        if self._internal_query_service is None:
            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def get_clients_by_ids(self, *, client_ids: list[int]) -> list[Client]:
        return self.internal_query_service.get_clients_by_ids(client_ids=client_ids)
