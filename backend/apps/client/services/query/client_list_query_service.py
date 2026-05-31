"""当事人列表查询服务。"""

from typing import Any

from django.db.models import QuerySet

from apps.client.models import Client
from apps.client.services.client_query_builder import ClientQueryBuilder

class ClientListQueryService:
    def __init__(self, query_builder: ClientQueryBuilder | None = None) -> None:
        self.query_builder = query_builder or ClientQueryBuilder()

    def list_clients(
        self,
        *,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: Any | None = None,
    ) -> QuerySet[Client, Client]:
        return self.query_builder.build_queryset(
            client_type=client_type,
            is_our_client=is_our_client,
            search=search,
        )
