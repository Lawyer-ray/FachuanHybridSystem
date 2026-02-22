"""
客户服务层
处理客户相关的业务逻辑（只读操作）
"""

from django.utils.translation import gettext_lazy as _
import logging
from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Q, QuerySet

from apps.core.config import get_config
from apps.core.exceptions import NotFoundError

from apps.client.models import Client

if TYPE_CHECKING:
    from .client_identity_doc_service import ClientIdentityDocService

logger = logging.getLogger("apps.client")


class ClientService:
    """
    客户服务（只读）

    职责：
    1. 封装客户查询相关的业务逻辑
    2. 优化数据库查询
    写操作请使用 ClientMutationService
    """

    def __init__(self, identity_doc_service: Optional["ClientIdentityDocService"] = None):
        """
        初始化服务

        Args:
            identity_doc_service: ClientIdentityDocService 实例，支持依赖注入
        """
        self._identity_doc_service = identity_doc_service

    @property
    def identity_doc_service(self) -> "ClientIdentityDocService":
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    def list_clients(
        self,
        page: int = 1,
        page_size: int | None = None,
        client_type: str | None = None,
        is_our_client: bool | None = None,
        search: str | None = None,
        user: Any = None,
    ) -> "QuerySet[Client, Client]":
        """
        获取客户列表

        Args:
            page: 页码
            page_size: 每页数量（如果为 None，使用配置的默认值）
            client_type: 客户类型过滤
            is_our_client: 是否我方当事人过滤
            search: 搜索关键词
            user: 当前用户

        Returns:
            客户查询集
        """
        # 获取分页配置
        if page_size is None:
            page_size = get_config("pagination.default_page_size", 20)

        # 验证分页参数
        max_page_size = get_config("pagination.max_page_size", 100)
        if page_size > max_page_size:
            page_size = max_page_size

        if not isinstance(page_size, int):
            page_size = int(page_size)  # type: ignore

        # 1. 构建基础查询（使用 prefetch_related 优化）
        queryset = Client.objects.prefetch_related("identity_docs").order_by("-id")

        # 2. 应用业务过滤
        if client_type:
            queryset = queryset.filter(client_type=client_type)

        if is_our_client is not None:
            queryset = queryset.filter(is_our_client=is_our_client)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(id_number__icontains=search)
            )

        # 3. 分页
        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

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

    def get_clients_by_ids(self, client_ids: list[int]) -> list[Client]:
        """
        批量获取客户

        Args:
            client_ids: 客户 ID 列表

        Returns:
            客户列表
        """
        return list(Client.objects.prefetch_related("identity_docs").filter(id__in=client_ids))

    def get_client_by_name(self, name: str) -> Client | None:
        """
        根据名称查询客户

        Args:
            name: 客户名称

        Returns:
            客户对象，不存在时返回 None
        """
        return Client.objects.filter(name=name).first()

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
