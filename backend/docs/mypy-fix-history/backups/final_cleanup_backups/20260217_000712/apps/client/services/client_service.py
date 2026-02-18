"""
客户服务层
处理客户相关的业务逻辑
"""
from typing import List, Optional, Dict, Any
from django.db.models import QuerySet, Q
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.core.interfaces import ClientDTO, IClientService
from apps.core.config import get_config
from ..models import Client
import logging

User = get_user_model()
logger = logging.getLogger("apps.client")


class ClientService:
    """
    客户服务

    职责：
    1. 封装客户相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 优化数据库查询
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
        page_size: Optional[int] = None,
        client_type: Optional[str] = None,
        is_our_client: Optional[bool] = None,
        search: Optional[str] = None,
        user: Optional[User] = None,
    ) -> QuerySet:
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
        
        # 1. 构建基础查询（使用 prefetch_related 优化）
        queryset = Client.objects.prefetch_related("identity_docs").order_by("-id")

        # 2. 应用业务过滤
        if client_type:
            queryset = queryset.filter(client_type=client_type)

        if is_our_client is not None:
            queryset = queryset.filter(is_our_client=is_our_client)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(phone__icontains=search) |
                Q(id_number__icontains=search)
            )

        # 3. 分页
        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

    def get_client(self, client_id: int, user: Optional[User] = None) -> Client:
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
        # 1. 查询客户（使用 prefetch_related 优化）
        client = Client.objects.prefetch_related("identity_docs").filter(
            id=client_id
        ).first()

        if not client:
            raise NotFoundError(
                message=f"客户不存在",
                code="CLIENT_NOT_FOUND"
            )

        return client

    def get_clients_by_ids(self, client_ids: List[int]) -> List[Client]:
        """
        批量获取客户

        Args:
            client_ids: 客户 ID 列表

        Returns:
            客户列表
        """
        return list(
            Client.objects.prefetch_related("identity_docs").filter(
                id__in=client_ids
            )
        )

    def get_client_by_name(self, name: str) -> Optional[Client]:
        """
        根据名称查询客户

        Args:
            name: 客户名称

        Returns:
            客户对象，不存在时返回 None
        """
        return Client.objects.filter(name=name).first()

    def _get_client_internal(self, client_id: int) -> Optional[Client]:
        """
        内部方法：无权限检查的客户查询
        供 Adapter 调用

        Args:
            client_id: 客户 ID

        Returns:
            客户对象，不存在时返回 None
        """
        return Client.objects.prefetch_related("identity_docs").filter(
            id=client_id
        ).first()

    def parse_client_text(self, text: str) -> Dict[str, Any]:
        """
        解析客户文本

        Args:
            text: 待解析的文本

        Returns:
            解析后的客户数据
        """
        from .text_parser import parse_client_text
        return parse_client_text(text)

    @transaction.atomic
    def create_client(self, data: Dict[str, Any], user: Optional[User] = None) -> Client:
        """
        创建客户

        Args:
            data: 客户数据
            user: 当前用户

        Returns:
            创建的客户对象

        Raises:
            ValidationException: 数据验证失败
            PermissionDenied: 权限不足
        """
        # 1. 权限检查
        if user and not self._check_create_permission(user):
            logger.warning(
                f"用户 {user.id} 尝试创建客户但权限不足",
                extra={"user_id": user.id, "action": "create_client"}
            )
            raise PermissionDenied(
                message="无权限创建客户",
                code="PERMISSION_DENIED"
            )

        # 2. 业务验证
        self._validate_create_data(data)

        # 3. 创建客户
        client = Client.objects.create(**data)

        # 4. 记录日志
        logger.info(
            f"客户创建成功",
            extra={
                "client_id": client.id,
                "user_id": user.id if user else None,
                "action": "create_client"
            }
        )

        return client

    @transaction.atomic
    def update_client(
        self,
        client_id: int,
        data: Dict[str, Any],
        user: Optional[User] = None
    ) -> Client:
        """
        更新客户

        Args:
            client_id: 客户 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的客户对象

        Raises:
            NotFoundError: 客户不存在
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        # 1. 获取客户
        client = self.get_client(client_id, user)

        # 2. 权限检查
        if user and not self._check_update_permission(user, client):
            logger.warning(
                f"用户 {user.id} 尝试更新客户 {client_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "client_id": client_id,
                    "action": "update_client"
                }
            )
            raise PermissionDenied(
                message="无权限更新该客户",
                code="PERMISSION_DENIED"
            )

        # 3. 业务验证
        self._validate_update_data(client, data)

        # 4. 更新字段
        for key, value in data.items():
            if hasattr(client, key):
                setattr(client, key, value)

        client.save()

        # 5. 记录日志
        logger.info(
            f"客户更新成功",
            extra={
                "client_id": client.id,
                "user_id": user.id if user else None,
                "action": "update_client"
            }
        )

        return client

    @transaction.atomic
    def delete_client(self, client_id: int, user: Optional[User] = None) -> None:
        """
        删除客户

        Args:
            client_id: 客户 ID
            user: 当前用户

        Raises:
            NotFoundError: 客户不存在
            PermissionDenied: 权限不足
        """
        # 1. 获取客户
        client = self.get_client(client_id, user)

        # 2. 权限检查
        if user and not self._check_delete_permission(user, client):
            logger.warning(
                f"用户 {user.id} 尝试删除客户 {client_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "client_id": client_id,
                    "action": "delete_client"
                }
            )
            raise PermissionDenied(
                message="无权限删除该客户",
                code="PERMISSION_DENIED"
            )

        # 3. 删除客户
        client.delete()

        # 4. 记录日志
        logger.info(
            f"客户删除成功",
            extra={
                "client_id": client_id,
                "user_id": user.id if user else None,
                "action": "delete_client"
            }
        )

    # ========== 私有方法（业务逻辑封装） ==========

    def _check_create_permission(self, user: User) -> bool:
        """检查创建权限（私有方法）"""
        return user.is_authenticated and (
            user.has_perm('client.add_client') or
            user.is_admin or
            user.is_superuser
        )

    def _check_update_permission(self, user: User, client: Client) -> bool:
        """检查更新权限（私有方法）"""
        return user.is_authenticated and (
            user.has_perm('client.change_client') or
            user.is_admin or
            user.is_superuser
        )

    def _check_delete_permission(self, user: User, client: Client) -> bool:
        """检查删除权限（私有方法）"""
        return user.is_authenticated and (
            user.has_perm('client.delete_client') or
            user.is_admin or
            user.is_superuser
        )

    def _validate_create_data(self, data: Dict[str, Any]) -> None:
        """验证创建数据（私有方法）"""
        # 验证必填字段
        if not data.get('name'):
            raise ValidationException(
                message="客户名称不能为空",
                code="INVALID_NAME",
                errors={"name": "客户名称不能为空"}
            )

        # 验证客户类型
        valid_types = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
        if data.get('client_type') not in valid_types:
            raise ValidationException(
                message="无效的客户类型",
                code="INVALID_CLIENT_TYPE",
                errors={"client_type": f"客户类型必须是: {', '.join(valid_types)}"}
            )

        # 验证法人必须有法定代表人
        if data.get('client_type') == Client.LEGAL and not data.get('legal_representative'):
            raise ValidationException(
                message="法人客户必须填写法定代表人",
                code="MISSING_LEGAL_REPRESENTATIVE",
                errors={"legal_representative": "法人客户必须填写法定代表人"}
            )

    def _validate_update_data(self, client: Client, data: Dict[str, Any]) -> None:
        """验证更新数据（私有方法）"""
        # 验证名称
        if 'name' in data and not data['name']:
            raise ValidationException(
                message="客户名称不能为空",
                code="INVALID_NAME",
                errors={"name": "客户名称不能为空"}
            )

        # 验证客户类型
        if 'client_type' in data:
            valid_types = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
            if data['client_type'] not in valid_types:
                raise ValidationException(
                    message="无效的客户类型",
                    code="INVALID_CLIENT_TYPE",
                    errors={"client_type": f"客户类型必须是: {', '.join(valid_types)}"}
                )

        # 验证法人必须有法定代表人
        client_type = data.get('client_type', client.client_type)
        legal_rep = data.get('legal_representative', client.legal_representative)
        if client_type == Client.LEGAL and not legal_rep:
            raise ValidationException(
                message="法人客户必须填写法定代表人",
                code="MISSING_LEGAL_REPRESENTATIVE",
                errors={"legal_representative": "法人客户必须填写法定代表人"}
            )


class ClientServiceAdapter(IClientService):
    """
    客户服务适配器
    实现跨模块接口，将 Model 转换为 DTO

    Requirements: 2.1, 2.2, 2.3
    """

    def __init__(self, client_service: Optional[ClientService] = None):
        """
        初始化适配器

        Args:
            client_service: ClientService 实例，如果为 None 则创建新实例
        """
        self.service = client_service or ClientService()

    def _to_dto(self, client: Client) -> ClientDTO:
        """将 Model 转换为 DTO"""
        return ClientDTO(
            id=client.id,
            name=client.name,
            client_type=client.client_type,
            phone=client.phone,
            id_number=client.id_number if hasattr(client, 'id_number') else None,
            address=client.address if hasattr(client, 'address') else None,
            is_our_client=client.is_our_client,
        )

    def get_client(self, client_id: int) -> Optional[ClientDTO]:
        """
        获取客户信息

        Args:
            client_id: 客户 ID

        Returns:
            客户 DTO，不存在时返回 None

        Requirements: 2.1
        """
        client = self.service._get_client_internal(client_id)
        if client:
            return self._to_dto(client)
        return None

    def get_clients_by_ids(self, client_ids: List[int]) -> List[ClientDTO]:
        """
        批量获取客户信息

        Args:
            client_ids: 客户 ID 列表

        Returns:
            客户 DTO 列表

        Requirements: 2.2
        """
        clients = self.service.get_clients_by_ids(client_ids)
        return [self._to_dto(c) for c in clients]

    def validate_client_exists(self, client_id: int) -> bool:
        """
        验证客户是否存在

        Args:
            client_id: 客户 ID

        Returns:
            客户是否存在

        Requirements: 2.4
        """
        client = self.service._get_client_internal(client_id)
        return client is not None

    def get_client_by_name(self, name: str) -> Optional[ClientDTO]:
        """
        根据名称获取客户

        Args:
            name: 客户名称

        Returns:
            客户 DTO，不存在时返回 None

        Requirements: 2.5
        """
        client = self.service.get_client_by_name(name)
        if client:
            return self._to_dto(client)
        return None

    def get_all_clients_internal(self) -> List[ClientDTO]:
        """
        内部方法：获取所有客户
        
        Returns:
            所有客户的 DTO 列表
        """
        clients = Client.objects.all()
        return [self._to_dto(client) for client in clients]

    def search_clients_by_name_internal(
        self, 
        name: str,
        exact_match: bool = False
    ) -> List[ClientDTO]:
        """
        内部方法：根据名称搜索客户
        
        Args:
            name: 客户名称或名称片段
            exact_match: 是否精确匹配（默认 False，支持模糊匹配）
            
        Returns:
            匹配的客户 DTO 列表
        """
        if not name:
            return []
        
        if exact_match:
            clients = Client.objects.filter(name=name)
        else:
            clients = Client.objects.filter(name__icontains=name)
        
        return [self._to_dto(client) for client in clients]
