"""
律所服务层
处理律所相关的业务逻辑
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ValidationException,
)
from apps.core.interfaces import ILawFirmService, LawFirmDTO
from apps.organization.dtos import LawFirmCreateDTO, LawFirmUpdateDTO
from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.dto_assemblers import LawFirmDtoAssembler
from apps.organization.services.access.organization_access_policy import OrganizationAccessPolicy

logger = logging.getLogger("apps.organization")


class LawFirmService:
    def __init__(self) -> None:
        self._access_policy = OrganizationAccessPolicy()

    def get_lawfirm_queryset(self) -> QuerySet[LawFirm, LawFirm]:
        return LawFirm.objects.all()

    def get_lawfirm(self, lawfirm_id: int, user: Lawyer | None) -> LawFirm:
        """
        获取律所

        Raises:
            AuthenticationError: 未认证
            NotFoundError: 律所不存在
            PermissionDenied: 无权限访问
        """
        if user is None:
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")

        lawfirm = self.get_lawfirm_by_id(lawfirm_id)

        if lawfirm is None:
            raise NotFoundError(message=_("律所不存在"), code="LAWFIRM_NOT_FOUND")

        if not self._access_policy.can_read_lawfirm(user, lawfirm):
            raise PermissionDenied(message=_("无权限访问该律所"), code="PERMISSION_DENIED")

        return lawfirm

    def list_lawfirms(
        self,
        page: int = 1,
        page_size: int = 20,
        name: str | None = None,
        user: Lawyer | None = None,
    ) -> QuerySet[LawFirm, LawFirm]:
        queryset = self.get_lawfirm_queryset()

        # 应用权限过滤
        if user and not user.is_superuser:
            if user.law_firm_id is not None:
                queryset = queryset.filter(id=user.law_firm_id)
            else:
                return queryset.none()

        # 应用业务过滤
        if name:
            queryset = queryset.filter(name__icontains=name)

        # 排序
        queryset = queryset.order_by("-id")

        # 分页
        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

    @transaction.atomic
    def create_lawfirm(self, data: LawFirmCreateDTO, user: Lawyer | None) -> LawFirm:
        """
        创建律所

        Raises:
            ValidationException: 数据验证失败
            AuthenticationError: 未认证
            PermissionDenied: 权限不足
        """
        # 0. 认证检查
        if user is None:
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")

        # 1. 权限检查
        if not self._access_policy.can_create(user):
            logger.warning(
                "用户 %s 尝试创建律所但权限不足",
                user.id,
                extra={"user_id": user.id, "action": "create_lawfirm"},
            )
            raise PermissionDenied(message=_("无权限创建律所"), code="PERMISSION_DENIED")

        # 2. 业务验证
        self._validate_create_data(data)

        # 3. 创建律所
        lawfirm = LawFirm.objects.create(
            name=data.name,
            address=data.address or "",
            phone=data.phone or "",
            social_credit_code=data.social_credit_code or "",
        )

        # 4. 记录日志
        logger.info("律所创建成功", extra={"lawfirm_id": lawfirm.id, "user_id": user.id, "action": "create_lawfirm"})

        return lawfirm

    @transaction.atomic
    def update_lawfirm(self, lawfirm_id: int, data: LawFirmUpdateDTO, user: Lawyer | None) -> LawFirm:
        """
        更新律所

        Raises:
            NotFoundError: 律所不存在
            AuthenticationError: 未认证
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        # 1. 获取律所（get_lawfirm 内部已做 None 检查）
        lawfirm = self.get_lawfirm(lawfirm_id, user)

        # user 经过 get_lawfirm 后必不为 None（get_lawfirm 对 None 抛 AuthenticationError）
        if user is None:  # pragma: no cover — 不可达，但消除 mypy 警告
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")

        # 2. 权限检查
        if not self._access_policy.can_update_lawfirm(user, lawfirm):
            logger.warning(
                "用户 %s 尝试更新律所 %s 但权限不足",
                user.id,
                lawfirm_id,
                extra={"user_id": user.id, "lawfirm_id": lawfirm_id, "action": "update_lawfirm"},
            )
            raise PermissionDenied(message=_("无权限更新该律所"), code="PERMISSION_DENIED")

        # 3. 业务验证
        self._validate_update_data(lawfirm, data)

        # 4. 更新字段
        updated_fields: list[str] = []
        if data.name is not None:
            lawfirm.name = data.name
            updated_fields.append("name")
        if data.address is not None:
            lawfirm.address = data.address
            updated_fields.append("address")
        if data.phone is not None:
            lawfirm.phone = data.phone
            updated_fields.append("phone")
        if data.social_credit_code is not None:
            lawfirm.social_credit_code = data.social_credit_code
            updated_fields.append("social_credit_code")

        if updated_fields:
            lawfirm.save(update_fields=updated_fields)

        # 5. 记录日志
        logger.info("律所更新成功", extra={"lawfirm_id": lawfirm.id, "user_id": user.id, "action": "update_lawfirm"})

        return lawfirm

    @transaction.atomic
    def delete_lawfirm(self, lawfirm_id: int, user: Lawyer | None) -> None:
        """
        删除律所

        Raises:
            NotFoundError: 律所不存在
            AuthenticationError: 未认证
            PermissionDenied: 权限不足
            ConflictError: 律所正在使用中
        """
        # 1. 获取律所（get_lawfirm 内部已做 None 检查）
        lawfirm = self.get_lawfirm(lawfirm_id, user)

        # user 经过 get_lawfirm 后必不为 None（get_lawfirm 对 None 抛 AuthenticationError）
        if user is None:  # pragma: no cover — 不可达，但消除 mypy 警告
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")

        # 2. 权限检查
        if not self._access_policy.can_delete_lawfirm(user, lawfirm):
            logger.warning(
                "用户 %s 尝试删除律所 %s 但权限不足",
                user.id,
                lawfirm_id,
                extra={"user_id": user.id, "lawfirm_id": lawfirm_id, "action": "delete_lawfirm"},
            )
            raise PermissionDenied(message=_("无权限删除该律所"), code="PERMISSION_DENIED")

        # 3. 业务验证（检查是否可以删除）
        if lawfirm.lawyers.exists():
            raise ConflictError(message=_("律所下还有律师，无法删除"), code="LAWFIRM_HAS_LAWYERS")

        if lawfirm.teams.exists():
            raise ConflictError(message=_("律所下还有团队，无法删除"), code="LAWFIRM_HAS_TEAMS")

        # 4. 删除律所
        lawfirm.delete()

        # 5. 记录日志
        logger.info("律所删除成功", extra={"lawfirm_id": lawfirm_id, "user_id": user.id, "action": "delete_lawfirm"})

    # ========== 私有方法（业务逻辑封装） ==========

    def _validate_create_data(self, data: LawFirmCreateDTO) -> None:
        # 检查名称是否重复
        if LawFirm.objects.filter(name=data.name).exists():
            raise ValidationException(
                message=_("律所名称已存在"), code="DUPLICATE_NAME", errors={"name": str(_("该名称已被使用"))}
            )

    def _validate_update_data(self, lawfirm: LawFirm, data: LawFirmUpdateDTO) -> None:
        # 检查名称是否与其他律所重复
        if data.name and data.name != lawfirm.name and LawFirm.objects.filter(name=data.name).exists():
            raise ValidationException(
                message=_("律所名称已存在"), code="DUPLICATE_NAME", errors={"name": str(_("该名称已被使用"))}
            )

    def get_lawfirm_by_id(self, lawfirm_id: int) -> LawFirm | None:
        """根据ID获取律所（公共方法，供Adapter层调用）"""
        return self.get_lawfirm_queryset().filter(id=lawfirm_id).first()


class LawFirmServiceAdapter(ILawFirmService):
    _assembler: ClassVar[LawFirmDtoAssembler] = LawFirmDtoAssembler()

    def __init__(self, lawfirm_service: LawFirmService | None = None) -> None:
        self.service = lawfirm_service or LawFirmService()

    def get_lawfirm(self, lawfirm_id: int) -> LawFirmDTO | None:
        lawfirm = self.service.get_lawfirm_by_id(lawfirm_id)
        if lawfirm is None:
            return None
        return self._assembler.to_dto(lawfirm)

    def get_lawfirms_by_ids(self, lawfirm_ids: list[int]) -> list[LawFirmDTO]:
        lawfirms = self.service.get_lawfirm_queryset().filter(id__in=lawfirm_ids)
        return [self._assembler.to_dto(lf) for lf in lawfirms]
