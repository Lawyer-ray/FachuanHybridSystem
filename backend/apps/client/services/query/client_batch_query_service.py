"""External service client."""

from typing import Any

from django.contrib.auth import get_user_model

from apps.client.models import Client
from apps.client.services.client_internal_query_service import ClientInternalQueryService

User = get_user_model()


class ClientBatchQueryService:
    def __init__(self, internal_query_service: ClientInternalQueryService | None = None) -> None:
        self._internal_query_service = internal_query_service

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
        if self._internal_query_service is None:
            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def get_clients_by_ids(self, *, client_ids: list[int], user: Any | None = None) -> list[Client]:
        return self.internal_query_service.get_clients_by_ids(client_ids=client_ids)
