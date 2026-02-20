"""External service client."""

from django.utils.translation import gettext_lazy as _
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.client.models import Client
from apps.client.services.client_query_builder import ClientQueryBuilder
from apps.core.exceptions import ValidationException

User = get_user_model()


class ClientListQueryService:
    def __init__(self, query_builder: ClientQueryBuilder | None = None) -> None:
        self.query_builder = query_builder or ClientQueryBuilder()

    def list_clients(
        self,
        *,
        page: int = 1,
        page_size: int | None = 20,
        max_page_size: int = 100,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: Any | None = None,
    ) -> QuerySet[Client, Client]:
        if page is None or int(page) < 1:
            raise ValidationException(message=_("page 无效"), code="INVALID_PAGE", errors={"page": "必须 >= 1"})

        if page_size is None:
            page_size = 20
        if int(page_size) < 1:
            raise ValidationException(
                message=_("page_size 无效"), code="INVALID_PAGE_SIZE", errors={"page_size": "必须 >= 1"}
            )
        page_size = int(page_size)

        if page_size > max_page_size:
            page_size = max_page_size

        queryset = self.query_builder.build_queryset(
            client_type=client_type,
            is_our_client=is_our_client,
            search=search,
        )

        start = (int(page) - 1) * page_size
        end = start + page_size
        return queryset[start:end]
