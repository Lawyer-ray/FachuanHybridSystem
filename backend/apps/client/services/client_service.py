"""当事人服务（只读查询 + 文本解析）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError

from apps.client.models import Client

if TYPE_CHECKING:
    from .client_identity_doc_service import ClientIdentityDocService

logger = logging.getLogger("apps.client")


class ClientService:
    """当事人服务（只读查询 + 文本解析）。"""

    def __init__(self, identity_doc_service: "ClientIdentityDocService | None" = None) -> None:
        self._identity_doc_service = identity_doc_service

    @property
    def identity_doc_service(self) -> "ClientIdentityDocService":
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    def get_client(self, client_id: int, user: Any = None) -> Client:
        """
        获取客户

        Args:
            client_id: 客户 ID
            user: 当前用户

        Returns:
            客户对象

        Raises:
            NotFoundError: 客户不存在
        """
        client: Client | None = Client.objects.prefetch_related("identity_docs").filter(id=client_id).first()

        if not client:
            raise NotFoundError(message=_("客户不存在"), code="CLIENT_NOT_FOUND")

        return client

    def _get_client_internal(self, client_id: int) -> Client | None:
        """
        内部方法：无权限检查的客户查询
        供 Adapter 调用

        Args:
            client_id: 客户 ID

        Returns:
            客户对象，不存在时返回 None
        """
        return Client.objects.prefetch_related("identity_docs").filter(id=client_id).first()

    def parse_client_text(self, text: str) -> dict[str, Any]:
        """
        解析客户文本

        Args:
            text: 待解析的文本

        Returns:
            解析后的客户数据
        """
        from .text_parser import parse_client_text

        return parse_client_text(text)

    def parse_multiple_clients_text(self, text: str) -> list[dict[str, Any]]:
        """
        解析包含多个客户的文本信息

        Args:
            text: 待解析的文本

        Returns:
            解析后的客户数据列表
        """
        from .text_parser import parse_multiple_clients_text

        return parse_multiple_clients_text(text)
