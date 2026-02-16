"""
律所服务层
处理律所相关的业务逻辑
"""
from typing import Optional, List
from django.db import transaction
from django.db.models import QuerySet, Count

from apps.core.exceptions import (
    ValidationException,
    PermissionDenied,
    NotFoundError,
    ConflictError
)
from apps.core.interfaces import LawFirmDTO, ILawFirmService
from ..models import LawFirm, Lawyer
from ..schemas import LawFirmIn, LawFirmUpdateIn
import logging

logger = logging.getLogger("apps.organization")


class LawFirmService:
    """
    律所服务

    职责：
    1. 封装律所相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 协调多个 Model 操作
    """

    def __init__(self):
        """初始化服务"""
        pass

    def get_lawfirm_queryset(self) -> QuerySet[LawFirm]:
        """
        获取带预加载的律所查询集

        Returns:
            律所查询集
        """
        return LawFirm.objects.prefetch_related('lawyers', 'teams')

    def get_lawfirm(self, lawfirm_id: int, user: Lawyer) -> LawFirm:
        """
        获取律所

        Args:
            lawfirm_id: 律所 ID
            user: 当前用户

        Returns:
            律所对象

        Raises:
            NotFoundError: 律所不存在
            PermissionDenied: 无权限访问
        """
        lawfirm = self.get_lawfirm_queryset().filter(id=lawfirm_id).first()

        if not lawfirm:
            raise NotFoundError(
                message=f"律所不存在",
                code="LAWFIRM_NOT_FOUND"
            )

        # 权限检查：用户可以访问自己所属的律所或管理员可以访问所有律所
        if not self._check_read_permission(user, lawfirm):
            raise PermissionDenied(
                message="无权限访问该律所",
                code="PERMISSION_DENIED"
            )

        return lawfirm

    def list_lawfirms(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict = None,
        user: Lawyer = None
    ) -> QuerySet[LawFirm]:
        """
        列表查询

        Args:
            page: 页码
            page_size: 每页数量
            filters: 过滤条件
            user: 当前用户

        Returns:
            律所查询集
        """
        filters = filters or {}

        # 构建基础查询（使用 prefetch_related 优化）
        queryset = self.get_lawfirm_queryset().annotate(
            lawyer_count=Count('lawyers')
        )

        # 应用权限过滤
        if user and not user.is_superuser:
            # 普通用户只能看到自己所属的律所
            queryset = queryset.filter(id=user.law_firm_id)

        # 应用业务过滤
        if filters.get('name'):
            queryset = queryset.filter(name__icontains=filters['name'])

        # 排序
        queryset = queryset.order_by('-id')

        # 分页
        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

    @transaction.atomic
    def create_lawfirm(self, data: LawFirmIn, user: Lawyer) -> LawFirm:
        """
        创建律所

        Args:
            data: 创建数据
            user: 当前用户

        Returns:
            创建的律所对象

        Raises:
            ValidationException: 数据验证失败
            PermissionDenied: 权限不足
        """
        # 1. 权限检查
        if not self._check_create_permission(user):
            logger.warning(
                f"用户 {user.id} 尝试创建律所但权限不足",
                extra={"user_id": user.id, "action": "create_lawfirm"}
            )
            raise PermissionDenied(
                message="无权限创建律所",
                code="PERMISSION_DENIED"
            )

        # 2. 业务验证
        self._validate_create_data(data)

        # 3. 创建律所
        lawfirm = LawFirm.objects.create(
            name=data.name,
            address=data.address or "",
            phone=data.phone or "",
            social_credit_code=data.social_credit_code or ""
        )

        # 4. 记录日志
        logger.info(
            f"律所创建成功",
            extra={
                "lawfirm_id": lawfirm.id,
                "user_id": user.id,
                "action": "create_lawfirm"
            }
        )

        return lawfirm

    @transaction.atomic
    def update_lawfirm(
        self,
        lawfirm_id: int,
        data: LawFirmUpdateIn,
        user: Lawyer
    ) -> LawFirm:
        """
        更新律所

        Args:
            lawfirm_id: 律所 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的律所对象

        Raises:
            NotFoundError: 律所不存在
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        # 1. 获取律所
        lawfirm = self.get_lawfirm(lawfirm_id, user)

        # 2. 权限检查
        if not self._check_update_permission(user, lawfirm):
            logger.warning(
                f"用户 {user.id} 尝试更新律所 {lawfirm_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "lawfirm_id": lawfirm_id,
                    "action": "update_lawfirm"
                }
            )
            raise PermissionDenied(
                message="无权限更新该律所",
                code="PERMISSION_DENIED"
            )

        # 3. 业务验证
        self._validate_update_data(lawfirm, data)

        # 4. 更新字段
        if data.name is not None:
            lawfirm.name = data.name
        if data.address is not None:
            lawfirm.address = data.address
        if data.phone is not None:
            lawfirm.phone = data.phone
        if data.social_credit_code is not None:
            lawfirm.social_credit_code = data.social_credit_code

        lawfirm.save()

        # 5. 记录日志
        logger.info(
            f"律所更新成功",
            extra={
                "lawfirm_id": lawfirm.id,
                "user_id": user.id,
                "action": "update_lawfirm"
            }
        )

        return lawfirm

    @transaction.atomic
    def delete_lawfirm(self, lawfirm_id: int, user: Lawyer) -> None:
        """
        删除律所

        Args:
            lawfirm_id: 律所 ID
            user: 当前用户

        Raises:
            NotFoundError: 律所不存在
            PermissionDenied: 权限不足
            ConflictError: 律所正在使用中
        """
        # 1. 获取律所
        lawfirm = self.get_lawfirm(lawfirm_id, user)

        # 2. 权限检查
        if not self._check_delete_permission(user, lawfirm):
            logger.warning(
                f"用户 {user.id} 尝试删除律所 {lawfirm_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "lawfirm_id": lawfirm_id,
                    "action": "delete_lawfirm"
                }
            )
            raise PermissionDenied(
                message="无权限删除该律所",
                code="PERMISSION_DENIED"
            )

        # 3. 业务验证（检查是否可以删除）
        if lawfirm.lawyers.exists():
            raise ConflictError(
                message="律所下还有律师，无法删除",
                code="LAWFIRM_HAS_LAWYERS"
            )

        if lawfirm.teams.exists():
            raise ConflictError(
                message="律所下还有团队，无法删除",
                code="LAWFIRM_HAS_TEAMS"
            )

        # 4. 删除律所
        lawfirm.delete()

        # 5. 记录日志
        logger.info(
            f"律所删除成功",
            extra={
                "lawfirm_id": lawfirm_id,
                "user_id": user.id,
                "action": "delete_lawfirm"
            }
        )

    # ========== 私有方法（业务逻辑封装） ==========

    def _check_create_permission(self, user: Lawyer) -> bool:
        """检查创建权限（私有方法）"""
        return user.is_authenticated and (user.is_superuser or user.is_admin)

    def _check_read_permission(self, user: Lawyer, lawfirm: LawFirm) -> bool:
        """检查读取权限（私有方法）"""
        # 超级管理员可以访问所有律所
        if user.is_superuser:
            return True

        # 用户可以访问自己所属的律所
        return user.law_firm_id == lawfirm.id

    def _check_update_permission(self, user: Lawyer, lawfirm: LawFirm) -> bool:
        """检查更新权限（私有方法）"""
        # 超级管理员或律所管理员可以更新
        return user.is_superuser or (user.is_admin and user.law_firm_id == lawfirm.id)

    def _check_delete_permission(self, user: Lawyer, lawfirm: LawFirm) -> bool:
        """检查删除权限（私有方法）"""
        # 只有超级管理员可以删除律所
        return user.is_superuser

    def _validate_create_data(self, data: LawFirmIn) -> None:
        """验证创建数据（私有方法）"""
        # 检查名称是否重复
        if LawFirm.objects.filter(name=data.name).exists():
            raise ValidationException(
                message="律所名称已存在",
                code="DUPLICATE_NAME",
                errors={"name": "该名称已被使用"}
            )

    def _validate_update_data(
        self,
        lawfirm: LawFirm,
        data: LawFirmUpdateIn
    ) -> None:
        """验证更新数据（私有方法）"""
        # 检查名称是否与其他律所重复
        if data.name and data.name != lawfirm.name:
            if LawFirm.objects.filter(name=data.name).exists():
                raise ValidationException(
                    message="律所名称已存在",
                    code="DUPLICATE_NAME",
                    errors={"name": "该名称已被使用"}
                )

    def _get_lawfirm_internal(self, lawfirm_id: int) -> Optional[LawFirm]:
        """
        内部方法：获取律所（无权限检查）

        供 ServiceAdapter 等内部组件调用，绕过权限检查。
        不应在 API 层直接调用此方法。

        Args:
            lawfirm_id: 律所 ID

        Returns:
            律所对象，不存在时返回 None
        """
        return self.get_lawfirm_queryset().filter(id=lawfirm_id).first()


class LawFirmServiceAdapter(ILawFirmService):
    """
    律所服务适配器
    实现跨模块接口，将 Model 转换为 DTO
    """

    def __init__(self, lawfirm_service: Optional[LawFirmService] = None):
        """
        初始化适配器（依赖注入）

        Args:
            lawfirm_service: 律所服务实例（可选，默认创建新实例）
        """
        self.service = lawfirm_service or LawFirmService()

    def _to_dto(self, lawfirm: LawFirm) -> LawFirmDTO:
        """将 Model 转换为 DTO"""
        return LawFirmDTO(
            id=lawfirm.id,
            name=lawfirm.name,
            address=lawfirm.address,
            phone=lawfirm.phone,
            social_credit_code=lawfirm.social_credit_code
        )

    def get_lawfirm(self, lawfirm_id: int) -> Optional[LawFirmDTO]:
        """获取律所信息"""
        lawfirm = self.service._get_lawfirm_internal(lawfirm_id)
        if not lawfirm:
            return None
        return self._to_dto(lawfirm)

    def get_lawfirms_by_ids(self, lawfirm_ids: List[int]) -> List[LawFirmDTO]:
        """批量获取律所信息"""
        lawfirms = LawFirm.objects.filter(id__in=lawfirm_ids)
        return [self._to_dto(lf) for lf in lawfirms]
