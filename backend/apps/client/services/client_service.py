"""当事人服务（只读查询 + 文本解析）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from apps.client.models import Client
    from .client_internal_query_service import ClientInternalQueryService

logger = logging.getLogger("apps.client")


class ClientService:
    """当事人服务（只读查询 + 文本解析）。"""

    def __init__(
        self,
        internal_query_service: ClientInternalQueryService | None = None,
    ) -> None:
        self._internal_query_service = internal_query_service

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
        """延迟获取 ClientInternalQueryService"""
        if self._internal_query_service is None:
            from .client_internal_query_service import ClientInternalQueryService

            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def get_client(self, client_id: int, user: Any = None) -> Client:
        """获取客户，不存在则抛出 NotFoundError。"""
        client = self.internal_query_service.get_client(client_id=client_id)
        if not client:
            raise NotFoundError(message=_("客户不存在"), code="CLIENT_NOT_FOUND")
        return client

    def parse_client_text(self, text: str) -> dict[str, Any]:
        """解析客户文本。"""
        from .text_parser import parse_client_text

        return parse_client_text(text)

    def parse_multiple_clients_text(self, text: str) -> list[dict[str, Any]]:
        """解析包含多个客户的文本信息。"""
        from .text_parser import parse_multiple_clients_text

        return parse_multiple_clients_text(text)
