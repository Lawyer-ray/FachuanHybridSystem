"""
律师指派服务层
处理合同律师指派相关的业务逻辑
"""
from typing import List, Optional, TYPE_CHECKING
from django.db import transaction
import logging

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import LawyerDTO
from ..models import Contract, ContractAssignment

if TYPE_CHECKING:
    from apps.core.interfaces import ILawyerService

logger = logging.getLogger("apps.contracts")


class LawyerAssignmentService:
    """
    律师指派服务

    职责：
    1. 管理合同律师指派关系
    2. 确保主办律师唯一性
    3. 维护律师排序
    4. 验证律师有效性
    """

    def __init__(self, lawyer_service: Optional["ILawyerService"] = None):
        """
        初始化服务（依赖注入）

        Args:
            lawyer_service: 律师服务接口（可选，延迟获取）
        """
        self._lawyer_service = lawyer_service

    @property
    def lawyer_service(self) -> "ILawyerService":
        """
        延迟获取律师服务

        Returns:
            ILawyerService 实例
        """
        if self._lawyer_service is None:
            from apps.core.interfaces import ServiceLocator
            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service

    @transaction.atomic
    def set_contract_lawyers(
        self,
        contract_id: int,
        lawyer_ids: List[int]
    ) -> List[ContractAssignment]:
        """
        设置合同律师（第一个为主办律师）

        业务规则：
        1. 删除现有的所有指派
        2. 按 lawyer_ids 顺序创建新指派
        3. 第一个律师设为主办（is_primary=True）
        4. 其余律师为协办（is_primary=False）
        5. order 字段按索引设置

        Args:
            contract_id: 合同 ID
            lawyer_ids: 律师 ID 列表（第一个为主办）

        Returns:
            创建的 ContractAssignment 列表

        Raises:
            NotFoundError: 合同不存在
            ValidationException: lawyer_ids 为空或律师不存在/已停用
        """
        # 验证 lawyer_ids 非空
        if not lawyer_ids:
            raise ValidationException(
                "至少需要指派一个律师",
                code="EMPTY_LAWYER_IDS",
                errors={"lawyer_ids": "至少需要指派一个律师"}
            )

        # 验证合同存在
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        # 验证所有律师存在且有效
        lawyer_dtos = self.lawyer_service.get_lawyers_by_ids(lawyer_ids)
        found_ids = {dto.id for dto in lawyer_dtos}
        missing_ids = set(lawyer_ids) - found_ids

        if missing_ids:
            raise ValidationException(
                f"律师不存在: {', '.join(map(str, missing_ids))}",
                code="LAWYER_NOT_FOUND",
                errors={"lawyer_ids": f"律师不存在: {', '.join(map(str, missing_ids))}"}
            )

        # 验证律师是否有效（is_active=True）
        inactive_lawyers = [
            dto.id for dto in lawyer_dtos
            if not dto.is_active
        ]
        if inactive_lawyers:
            raise ValidationException(
                f"律师已停用: {', '.join(map(str, inactive_lawyers))}",
                code="LAWYER_INACTIVE",
                errors={"lawyer_ids": f"律师已停用: {', '.join(map(str, inactive_lawyers))}"}
            )

        # 删除现有指派
        ContractAssignment.objects.filter(contract_id=contract_id).delete()

        # 创建新指派
        assignments = []
        for index, lawyer_id in enumerate(lawyer_ids):
            assignment = ContractAssignment.objects.create(
                contract=contract,
                lawyer_id=lawyer_id,
                is_primary=(index == 0),  # 第一个为主办
                order=index
            )
            assignments.append(assignment)

        logger.info(
            f"合同律师指派成功",
            extra={
                "contract_id": contract_id,
                "lawyer_ids": lawyer_ids,
                "primary_lawyer_id": lawyer_ids[0],
                "action": "set_contract_lawyers"
            }
        )

        return assignments

    @transaction.atomic
    def set_primary_lawyer(
        self,
        contract_id: int,
        lawyer_id: int
    ) -> ContractAssignment:
        """
        设置主办律师

        业务规则：
        1. 将指定律师设为主办（is_primary=True）
        2. 自动将其他律师的 is_primary 设为 False
        3. 如果律师不在指派列表中，先添加再设为主办

        Args:
            contract_id: 合同 ID
            lawyer_id: 律师 ID

        Returns:
            更新后的 ContractAssignment

        Raises:
            NotFoundError: 合同不存在
            ValidationException: 律师不存在或已停用
        """
        # 验证合同存在
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        # 验证律师存在且有效
        lawyer_dto = self.lawyer_service.get_lawyer(lawyer_id)
        if not lawyer_dto:
            raise ValidationException(
                f"律师 {lawyer_id} 不存在",
                code="LAWYER_NOT_FOUND",
                errors={"lawyer_id": f"律师 {lawyer_id} 不存在"}
            )

        if not lawyer_dto.is_active:
            raise ValidationException(
                f"律师 {lawyer_id} 已停用",
                code="LAWYER_INACTIVE",
                errors={"lawyer_id": f"律师 {lawyer_id} 已停用"}
            )

        # 将所有指派的 is_primary 设为 False
        ContractAssignment.objects.filter(
            contract_id=contract_id
        ).update(is_primary=False)

        # 获取或创建指派，并设为主办
        assignment, created = ContractAssignment.objects.get_or_create(
            contract=contract,
            lawyer_id=lawyer_id,
            defaults={"is_primary": True, "order": 0}
        )

        if not created:
            assignment.is_primary = True
            assignment.save(update_fields=["is_primary"])

        logger.info(
            f"主办律师设置成功",
            extra={
                "contract_id": contract_id,
                "lawyer_id": lawyer_id,
                "created": created,
                "action": "set_primary_lawyer"
            }
        )

        return assignment

    def get_primary_lawyer(self, contract_id: int) -> Optional[LawyerDTO]:
        """
        获取主办律师

        Args:
            contract_id: 合同 ID

        Returns:
            主办律师 DTO，不存在时返回 None

        Raises:
            NotFoundError: 合同不存在
        """
        # 验证合同存在
        try:
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        # 查询主办律师
        assignment = ContractAssignment.objects.filter(
            contract_id=contract_id,
            is_primary=True
        ).select_related("lawyer").first()

        if assignment:
            return LawyerDTO.from_model(assignment.lawyer)
        
        return None

    def get_all_lawyers(self, contract_id: int) -> List[LawyerDTO]:
        """
        获取合同的所有律师（按 is_primary 降序、order 升序）

        Args:
            contract_id: 合同 ID

        Returns:
            律师 DTO 列表

        Raises:
            NotFoundError: 合同不存在
        """
        # 验证合同存在
        try:
            Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            raise NotFoundError(f"合同 {contract_id} 不存在")

        # 查询所有指派（已按 Meta.ordering 排序）
        assignments = ContractAssignment.objects.filter(
            contract_id=contract_id
        ).select_related("lawyer")

        return [LawyerDTO.from_model(assignment.lawyer) for assignment in assignments]
