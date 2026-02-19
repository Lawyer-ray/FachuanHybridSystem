"""Business logic services."""

from __future__ import annotations

"""
案件案号服务层
处理案件案号相关的业务逻辑
"""

import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.cases.models import Case, CaseNumber
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.utils import normalize_case_number as normalize_case_number_util
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import ICaseService
from apps.core.security import DjangoPermsMixin

from .wiring import get_case_service

logger = logging.getLogger("apps.cases")  # type: ignore[call-arg]


class CaseNumberService(DjangoPermsMixin):
    """
    案件案号服务

    职责:
    1. 封装案件案号相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    5. 案号规范化处理
    """

    def __init__(self, case_service: ICaseService | None = None) -> None:
        """
        初始化服务(依赖注入)

        Args:
            case_service: 案件服务接口(注入)
        """
        self._case_service = case_service
        self._access_policy: CaseAccessPolicy | None = None

    @property
    def case_service(self) -> ICaseService:
        """延迟加载:优先使用注入实例"""
        if self._case_service is None:
            self._case_service = get_case_service()
        return self._case_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    def _require_case_access(
        self, case_id: int, user: Any | None, org_access: dict[str, Any] | None, perm_open_access: bool
    ) -> None:
        self.access_policy.ensure_access(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            message="无权限访问此案件",
        )

    def list_numbers(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        """
        获取案号列表

        Args:
            case_id: 案件 ID(可选,用于过滤)
            user: 当前用户

        Returns:
            案号查询集
        """
        qs = CaseNumber.objects.select_related("case").order_by("created_at")

        # 应用过滤条件
        if case_id:
            self._require_case_access(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
            qs = qs.filter(case_id=case_id)
        else:
            if not perm_open_access:
                self.ensure_authenticated(user)
                if not (self.is_admin(user) or self.is_superuser(user)):
                    allowed_case_ids = self.access_policy.filter_queryset(
                        Case.objects.all(),
                        user=user,
                        org_access=org_access,
                        perm_open_access=perm_open_access,
                    ).values_list("id", flat=True)
                    qs = qs.filter(case_id__in=list(allowed_case_ids))

        logger.debug(
            "获取案号列表",
            extra={
                "action": "list_numbers",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
                "count": qs.count(),
            },
        )

        return qs

    def get_number(
        self,
        number_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseNumber:
        """
        获取单个案号

        Args:
            number_id: 案号 ID
            user: 当前用户

        Returns:
            案号对象

        Raises:
            NotFoundError: 案号不存在
        """
        try:
            case_number = CaseNumber.objects.select_related("case").get(id=number_id)
            self._require_case_access(
                case_number.case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
            )

            logger.debug(
                "获取案号成功",
                extra={
                    "action": "get_number",
                    "number_id": number_id,
                    "case_id": case_number.case_id,
                    "number": case_number.number,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )

            return cast(CaseNumber, case_number)
        except CaseNumber.DoesNotExist:
            logger.warning(
                "案号不存在",
                extra={
                    "action": "get_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"},
            ) from None

    @transaction.atomic
    def create_number(
        self,
        case_id: int,
        number: str,
        remarks: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseNumber:
        """
        创建案号(自动规范化)

        Args:
            case_id: 案件 ID
            number: 案号
            remarks: 备注(可选)
            user: 当前用户

        Returns:
            创建的案号对象

        Raises:
            NotFoundError: 案件不存在
            ValidationException: 数据验证失败
        """
        self._require_case_access(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        # 验证案件是否存在
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            logger.warning(
                "创建案号失败:案件不存在",
                extra={
                    "action": "create_number",
                    "case_id": case_id,
                    "number": number,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            ) from None

        # 验证案号不能为空
        if not number or not number.strip():
            raise ValidationException(
                message="案号不能为空", code="INVALID_CASE_NUMBER", errors={"number": "案号不能为空"}
            )

        # 规范化案号
        normalized_number = self.normalize_case_number(number)  # type: ignore[call-arg, misc]

        # 创建案号
        case_number = CaseNumber.objects.create(case=case, number=normalized_number, remarks=remarks)

        logger.info(
            "创建案号成功",
            extra={
                "action": "create_number",
                "number_id": cast(int, case_number.id),
                "case_id": case_id,
                "original_number": number,
                "normalized_number": normalized_number,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return case_number

    @transaction.atomic
    def update_number(
        self,
        number_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseNumber:
        """
        更新案号

        Args:
            number_id: 案号 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的案号对象

        Raises:
            NotFoundError: 案号不存在
            ValidationException: 数据验证失败
        """
        try:
            case_number = CaseNumber.objects.select_related("case").get(id=number_id)
        except CaseNumber.DoesNotExist:
            logger.warning(
                "更新案号失败:案号不存在",
                extra={
                    "action": "update_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"},
            ) from None

        self._require_case_access(
            case_number.case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

        # 验证案件是否存在(如果更新了 case_id)
        case_id = data.get("case_id")
        if case_id and case_id != case_number.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist:
                raise NotFoundError(
                    message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
                ) from None
            self._require_case_access(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        # 规范化案号(如果更新了 number)
        number = data.get("number")
        if number is not None:
            if not number or not number.strip():
                raise ValidationException(
                    message="案号不能为空", code="INVALID_CASE_NUMBER", errors={"number": "案号不能为空"}
                )
            data["number"] = self.normalize_case_number(number)

        # 更新案号
        original_number = case_number.number
        for key, value in data.items():
            if hasattr(case_number, key):
                setattr(case_number, key, value)

        case_number.save()

        logger.info(
            "更新案号成功",
            extra={
                "action": "update_number",
                "number_id": number_id,
                "case_id": case_number.case_id,
                "original_number": original_number,
                "new_number": case_number.number,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return case_number  # type: ignore[no-any-return]

    @transaction.atomic
    def delete_number(
        self,
        number_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """
        删除案号

        Args:
            number_id: 案号 ID
            user: 当前用户

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 案号不存在
        """
        try:
            case_number = CaseNumber.objects.get(id=number_id)
        except CaseNumber.DoesNotExist:
            logger.warning(
                "删除案号失败:案号不存在",
                extra={
                    "action": "delete_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"},
            ) from None

        self._require_case_access(
            case_number.case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

        case_id = case_number.case_id
        number = case_number.number

        case_number.delete()

        logger.info(
            "删除案号成功",
            extra={
                "action": "delete_number",
                "number_id": number_id,
                "case_id": case_id,
                "number": number,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return {"success": True}

    def normalize_case_number(number: str) -> str:  # type: ignore[misc]
        """
        规范化案号:统一括号、删除空格

        处理规则:
        1. 英文括号 () 转中文括号 ()
        2. 六角括号 〔〕 转中文括号 ()
        3. 中括号 [] 转中文括号 ()
        4. 删除所有空格(包括全角空格)

        Args:
        number: 原始案号

        Returns:
        规范化后的案号
        """
        return normalize_case_number_util(number, ensure_hao=False)
