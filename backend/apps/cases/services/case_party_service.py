"""
案件当事人服务层
处理案件当事人相关的业务逻辑
"""
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from django.db import transaction
from django.db.models import QuerySet
import logging

from apps.core.exceptions import NotFoundError, ConflictError, ValidationException
from apps.core.interfaces import ICaseService, IClientService, IContractService, ServiceLocator
from ..models import CaseParty, Case

if TYPE_CHECKING:
    pass

logger = logging.getLogger("apps.cases")


class CasePartyService:
    """
    案件当事人服务

    职责：
    1. 封装案件当事人相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    """

    def __init__(
        self,
        case_service: Optional[ICaseService] = None,
        client_service: Optional[IClientService] = None,
        contract_service: Optional[IContractService] = None,
    ):
        """
        初始化服务（依赖注入）

        Args:
            case_service: 案件服务接口（注入）
            client_service: 客户服务接口（注入）
            contract_service: 合同服务接口（注入）
        """
        self._case_service = case_service
        self._client_service = client_service
        self._contract_service = contract_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载：优先使用注入实例"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    @property
    def client_service(self) -> IClientService:
        """延迟加载：优先使用注入实例"""
        if self._client_service is None:
            self._client_service = ServiceLocator.get_client_service()
        return self._client_service

    @property
    def contract_service(self) -> IContractService:
        """延迟加载：优先使用注入实例"""
        if self._contract_service is None:
            self._contract_service = ServiceLocator.get_contract_service()
        return self._contract_service

    def validate_party_in_contract_scope(
        self,
        case_id: int,
        client_id: int,
    ) -> bool:
        """
        验证当事人是否在案件绑定合同的范围内

        当案件绑定了合同时，验证 client 是否属于该合同或其补充协议的当事人。
        当案件未绑定合同时，允许任意 client。

        Args:
            case_id: 案件 ID
            client_id: 客户 ID

        Returns:
            True 如果验证通过（无合同或在范围内）

        Raises:
            ValidationException: 当事人不在合同范围内
            NotFoundError: 案件不存在

        Requirements: 4.1, 4.2, 4.3
        """
        # 获取案件
        try:
            case = Case.objects.select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            logger.warning(
                f"验证当事人范围失败：案件不存在",
                extra={
                    "action": "validate_party_in_contract_scope",
                    "case_id": case_id,
                    "client_id": client_id,
                }
            )
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )

        # 如果案件未绑定合同，允许任意当事人 (Requirements 4.3)
        if case.contract_id is None:
            logger.debug(
                f"案件未绑定合同，允许任意当事人",
                extra={
                    "action": "validate_party_in_contract_scope",
                    "case_id": case_id,
                    "client_id": client_id,
                }
            )
            return True

        # 获取合同的所有当事人
        try:
            all_parties = self.contract_service.get_all_parties(case.contract_id)
        except NotFoundError:
            # 合同不存在，理论上不应该发生（外键约束）
            logger.error(
                f"验证当事人范围失败：合同不存在",
                extra={
                    "action": "validate_party_in_contract_scope",
                    "case_id": case_id,
                    "contract_id": case.contract_id,
                    "client_id": client_id,
                }
            )
            raise ValidationException(
                message="关联合同不存在",
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": f"案件关联的合同 {case.contract_id} 不存在"}
            )

        # 检查 client_id 是否在合同当事人范围内 (Requirements 4.1)
        valid_client_ids = {party["id"] for party in all_parties}

        if client_id not in valid_client_ids:
            logger.warning(
                f"当事人不在合同范围内",
                extra={
                    "action": "validate_party_in_contract_scope",
                    "case_id": case_id,
                    "contract_id": case.contract_id,
                    "client_id": client_id,
                    "valid_client_ids": list(valid_client_ids),
                }
            )
            # Requirements 4.2: 抛出 ValidationException
            raise ValidationException(
                message="当事人必须属于绑定合同的当事人范围",
                code="PARTY_NOT_IN_CONTRACT_SCOPE",
                errors={"client_id": "当事人必须属于绑定合同的当事人范围"}
            )

        logger.debug(
            f"当事人在合同范围内，验证通过",
            extra={
                "action": "validate_party_in_contract_scope",
                "case_id": case_id,
                "contract_id": case.contract_id,
                "client_id": client_id,
            }
        )
        return True

    def list_parties(
        self,
        case_id: Optional[int] = None,
        user: Optional[Any] = None,
    ) -> QuerySet:
        """
        获取当事人列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
            user: 当前用户

        Returns:
            当事人查询集
        """
        qs = CaseParty.objects.select_related(
            "case",
            "client"
        ).order_by("-id")

        # 应用过滤条件
        if case_id:
            qs = qs.filter(case_id=case_id)

        logger.debug(
            f"获取当事人列表",
            extra={
                "action": "list_parties",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
                "count": qs.count()
            }
        )

        return qs

    def get_party(
        self,
        party_id: int,
        user: Optional[Any] = None,
    ) -> CaseParty:
        """
        获取单个当事人

        Args:
            party_id: 当事人 ID
            user: 当前用户

        Returns:
            当事人对象

        Raises:
            NotFoundError: 当事人不存在
        """
        try:
            party = CaseParty.objects.select_related(
                "case",
                "client"
            ).get(id=party_id)

            logger.debug(
                f"获取当事人成功",
                extra={
                    "action": "get_party",
                    "party_id": party_id,
                    "case_id": party.case_id,
                    "client_id": party.client_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )

            return party
        except CaseParty.DoesNotExist:
            logger.warning(
                f"当事人不存在",
                extra={
                    "action": "get_party",
                    "party_id": party_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="当事人不存在",
                code="PARTY_NOT_FOUND",
                errors={"party_id": f"ID 为 {party_id} 的当事人不存在"}
            )

    @transaction.atomic
    def create_party(
        self,
        case_id: int,
        client_id: int,
        legal_status: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> CaseParty:
        """
        创建当事人

        Args:
            case_id: 案件 ID
            client_id: 客户 ID
            legal_status: 诉讼地位（可选）
            user: 当前用户

        Returns:
            创建的当事人对象

        Raises:
            NotFoundError: 案件或客户不存在
            ConflictError: 当事人已存在
            ValidationException: 数据验证失败
        """
        # 验证案件是否存在
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            logger.warning(
                f"创建当事人失败：案件不存在",
                extra={
                    "action": "create_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )

        # 验证客户是否存在
        if not self.client_service.validate_client_exists(client_id):
            logger.warning(
                f"创建当事人失败：客户不存在",
                extra={
                    "action": "create_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="客户不存在",
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的客户不存在"}
            )

        # 检查是否已存在相同的当事人（重复检测）
        if CaseParty.objects.filter(case_id=case_id, client_id=client_id).exists():
            logger.warning(
                f"创建当事人失败：当事人已存在",
                extra={
                    "action": "create_party",
                    "case_id": case_id,
                    "client_id": client_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise ConflictError(
                message="当事人已存在",
                code="PARTY_ALREADY_EXISTS",
                errors={"party": f"案件 {case_id} 中已存在客户 {client_id} 的当事人记录"}
            )

        # 验证当事人是否在合同范围内 (Requirements 4.1, 4.2, 4.3)
        # 注意：validate_party_in_contract_scope 会在验证失败时抛出 ValidationException
        self.validate_party_in_contract_scope(case_id, client_id)

        # 创建当事人
        party = CaseParty.objects.create(
            case=case,
            client_id=client_id,
            legal_status=legal_status
        )

        logger.info(
            f"创建当事人成功",
            extra={
                "action": "create_party",
                "party_id": party.id,
                "case_id": case_id,
                "client_id": client_id,
                "legal_status": legal_status,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return party

    @transaction.atomic
    def update_party(
        self,
        party_id: int,
        data: Dict[str, Any],
        user: Optional[Any] = None,
    ) -> CaseParty:
        """
        更新当事人

        Args:
            party_id: 当事人 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的当事人对象

        Raises:
            NotFoundError: 当事人不存在
            ValidationException: 数据验证失败
        """
        try:
            party = CaseParty.objects.select_related("case").get(id=party_id)
        except CaseParty.DoesNotExist:
            logger.warning(
                f"更新当事人失败：当事人不存在",
                extra={
                    "action": "update_party",
                    "party_id": party_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="当事人不存在",
                code="PARTY_NOT_FOUND",
                errors={"party_id": f"ID 为 {party_id} 的当事人不存在"}
            )

        # 验证案件是否存在（如果更新了 case_id）
        case_id = data.get("case_id")
        if case_id and case_id != party.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist:
                raise NotFoundError(
                    message="案件不存在",
                    code="CASE_NOT_FOUND",
                    errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
                )

        # 验证客户是否存在（如果更新了 client_id）
        client_id = data.get("client_id")
        if client_id and client_id != party.client_id:
            if not self.client_service.validate_client_exists(client_id):
                raise NotFoundError(
                    message="客户不存在",
                    code="CLIENT_NOT_FOUND",
                    errors={"client_id": f"ID 为 {client_id} 的客户不存在"}
                )

        # 检查重复当事人（如果更新了 case_id 或 client_id）
        new_case_id = data.get("case_id", party.case_id)
        new_client_id = data.get("client_id", party.client_id)

        if (new_case_id != party.case_id or new_client_id != party.client_id):
            if CaseParty.objects.filter(
                case_id=new_case_id,
                client_id=new_client_id
            ).exclude(id=party_id).exists():
                raise ConflictError(
                    message="当事人已存在",
                    code="PARTY_ALREADY_EXISTS",
                    errors={"party": f"案件 {new_case_id} 中已存在客户 {new_client_id} 的当事人记录"}
                )

        # 更新当事人
        for key, value in data.items():
            if hasattr(party, key):
                setattr(party, key, value)

        party.save()

        logger.info(
            f"更新当事人成功",
            extra={
                "action": "update_party",
                "party_id": party_id,
                "case_id": party.case_id,
                "client_id": party.client_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return party

    @transaction.atomic
    def delete_party(
        self,
        party_id: int,
        user: Optional[Any] = None,
    ) -> Dict[str, bool]:
        """
        删除当事人

        Args:
            party_id: 当事人 ID
            user: 当前用户

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 当事人不存在
        """
        try:
            party = CaseParty.objects.get(id=party_id)
        except CaseParty.DoesNotExist:
            logger.warning(
                f"删除当事人失败：当事人不存在",
                extra={
                    "action": "delete_party",
                    "party_id": party_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="当事人不存在",
                code="PARTY_NOT_FOUND",
                errors={"party_id": f"ID 为 {party_id} 的当事人不存在"}
            )

        case_id = party.case_id
        client_id = party.client_id

        party.delete()

        logger.info(
            f"删除当事人成功",
            extra={
                "action": "delete_party",
                "party_id": party_id,
                "case_id": case_id,
                "client_id": client_id,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return {"success": True}