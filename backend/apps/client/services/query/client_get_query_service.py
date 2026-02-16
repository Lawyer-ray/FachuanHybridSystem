"""External service client."""

from typing import Any

from django.contrib.auth import get_user_model

from apps.client.models import Client
from apps.client.services.client_internal_query_service import ClientInternalQueryService
from apps.core.exceptions import NotFoundError

User = get_user_model()


class ClientGetQueryService:
    def __init__(self, internal_query_service: ClientInternalQueryService | None = None) -> None:
        self._internal_query_service = internal_query_service

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
        if self._internal_query_service is None:
            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def get_client(self, *, client_id: int, user: Any | None = None) -> Client:
        client = self.internal_query_service.get_client(client_id=client_id)
        if not client:
            raise NotFoundError(message="客户不存在", code="CLIENT_NOT_FOUND")
        return client
