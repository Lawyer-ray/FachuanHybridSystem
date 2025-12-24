"""
补充协议服务层
处理补充协议相关的业务逻辑
"""
from typing import List, Optional, Dict, Any
from django.db import transaction, IntegrityError
import logging

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import IClientService, ServiceLocator
from ..models import (
    Contract,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)

logger = logging.getLogger("apps.contracts")


class SupplementaryAgreementService:
    """
    补充协议服务

    职责：
    1. 补充协议的 CRUD 操作
    2. 当事人关联管理
    3. 数据验证和业务逻辑
    4. 事务管理

    注意：
    - 使用依赖注入访问客户服务
    - 使用 @transaction.atomic 保证数据一致性
    - 抛出自定义异常（NotFoundError, ValidationException）
    """

    def __init__(self, client_service: Optional[IClientService] = None):
        """
        初始化服务

        Args:
            client_service: 客户服务接口（可选，用于依赖注入）
        """
        self._client_service = client_service

    @property
    def client_service(self) -> IClientService:
        """延迟获取客户服务"""
        if self._client_service is None:
            self._client_service = ServiceLocator.get_client_service()
        return self._client_service

    @transaction.atomic
    def create_supplementary_agreement(
        self,
        contract_id: int,
        name: Optional[str],
        party_ids: Optional[List[int]]
    ) -> SupplementaryAgreement:
        """
        创建补充协议

        Args:
            contract_id: 合同 ID
            name: 补充协议名称（可为空）
            party_ids: 当事人 ID 列表（可为空）

        Returns:
            创建的补充协议实例

        Raises:
            NotFoundError: 合同或客户不存在
            ValidationException: 数据验证失败
        """
        # 1. 验证合同存在
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError("合同不存在")

        # 2. 创建补充协议
        agreement = SupplementaryAgreement.objects.create(
            contract=contract,
            name=name
        )

        # 3. 添加当事人关联
        if party_ids:
            self._add_parties(agreement, party_ids)

        # 4. 记录日志
        logger.info(
            "补充协议创建成功",
            extra={
                "agreement_id": agreement.id,
                "contract_id": contract_id,
                "party_count": len(party_ids) if party_ids else 0,
                "action": "create_supplementary_agreement"
            }
        )

        return agreement

    @transaction.atomic
    def update_supplementary_agreement(
        self,
        agreement_id: int,
        name: Optional[str] = None,
        party_ids: Optional[List[int]] = None
    ) -> SupplementaryAgreement:
        """
        更新补充协议

        Args:
            agreement_id: 补充协议 ID
            name: 新名称（可选）
            party_ids: 新当事人列表（可选，会替换现有当事人）

        Returns:
            更新后的补充协议实例

        Raises:
            NotFoundError: 补充协议或客户不存在
            ValidationException: 数据验证失败
        """
        # 1. 获取补充协议
        try:
            agreement = SupplementaryAgreement.objects.get(id=agreement_id)
        except SupplementaryAgreement.DoesNotExist:
            raise NotFoundError("补充协议不存在")

        # 2. 更新名称
        if name is not None:
            agreement.name = name
            agreement.save()

        # 3. 更新当事人（如果提供）
        if party_ids is not None:
            # 删除现有当事人
            agreement.parties.all().delete()
            # 添加新当事人
            if party_ids:
                self._add_parties(agreement, party_ids)

        # 4. 记录日志
        logger.info(
            "补充协议更新成功",
            extra={
                "agreement_id": agreement_id,
                "updated_fields": {
                    "name": name is not None,
                    "parties": party_ids is not None
                },
                "action": "update_supplementary_agreement"
            }
        )

        return agreement

    def get_supplementary_agreement(
        self,
        agreement_id: int,
        prefetch: bool = True
    ) -> SupplementaryAgreement:
        """
        获取补充协议

        Args:
            agreement_id: 补充协议 ID
            prefetch: 是否预加载关联数据

        Returns:
            补充协议实例

        Raises:
            NotFoundError: 补充协议不存在
        """
        try:
            qs = SupplementaryAgreement.objects
            if prefetch:
                qs = qs.select_related("contract").prefetch_related(
                    "parties__client"
                )
            return qs.get(id=agreement_id)
        except SupplementaryAgreement.DoesNotExist:
            raise NotFoundError("补充协议不存在")

    def list_by_contract(
        self,
        contract_id: int,
        prefetch: bool = True
    ) -> List[SupplementaryAgreement]:
        """
        获取合同的所有补充协议

        Args:
            contract_id: 合同 ID
            prefetch: 是否预加载关联数据

        Returns:
            补充协议列表
        """
        qs = SupplementaryAgreement.objects.filter(contract_id=contract_id)
        if prefetch:
            qs = qs.prefetch_related("parties__client")
        return list(qs.order_by("-created_at"))

    @transaction.atomic
    def delete_supplementary_agreement(self, agreement_id: int) -> None:
        """
        删除补充协议

        Args:
            agreement_id: 补充协议 ID

        Raises:
            NotFoundError: 补充协议不存在
        """
        try:
            agreement = SupplementaryAgreement.objects.get(id=agreement_id)
            agreement.delete()

            logger.info(
                "补充协议删除成功",
                extra={
                    "agreement_id": agreement_id,
                    "action": "delete_supplementary_agreement"
                }
            )
        except SupplementaryAgreement.DoesNotExist:
            raise NotFoundError("补充协议不存在")

    def _add_parties(
        self,
        agreement: SupplementaryAgreement,
        party_ids: List[int]
    ) -> None:
        """
        添加当事人关联（内部方法）

        Args:
            agreement: 补充协议实例
            party_ids: 客户 ID 列表

        Raises:
            NotFoundError: 客户不存在
            ValidationException: 重复添加客户
        """
        # 验证所有客户存在（通过接口）
        clients = self.client_service.get_clients_by_ids(party_ids)
        if len(clients) != len(party_ids):
            raise NotFoundError("部分客户不存在")

        # 批量创建当事人关联
        parties = [
            SupplementaryAgreementParty(
                supplementary_agreement=agreement,
                client_id=client_id
            )
            for client_id in party_ids
        ]

        try:
            SupplementaryAgreementParty.objects.bulk_create(
                parties,
                batch_size=100
            )
        except IntegrityError:
            raise ValidationException("不能重复添加同一客户")
