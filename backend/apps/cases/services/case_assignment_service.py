"""
案件指派服务层
处理案件指派相关的业务逻辑
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
import logging
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.core.exceptions import ConflictError, NotFoundError
from apps.core.interfaces import ICaseService, IContractAssignmentQueryService, ServiceLocator

from apps.cases.models import Case, CaseAssignment

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User

logger = logging.getLogger("apps.cases")


class CaseAssignmentService:
    """
    案件指派服务

    职责：
    1. 封装案件指派相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    """

    def __init__(
        self,
        case_service: ICaseService | None = None,
        contract_assignment_query_service: IContractAssignmentQueryService | None = None,
    ):
        """
        初始化服务（依赖注入）

        Args:
            case_service: 案件服务接口（注入）
            contract_assignment_query_service: 合同指派查询服务接口（注入）
        """
        self._case_service = case_service
        self._contract_assignment_query_service = contract_assignment_query_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载：优先使用注入实例"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    def list_assignments(
        self,
        case_id: int | None = None,
        lawyer_id: int | None = None,
        user: User | None = None,
    ) -> QuerySet[CaseAssignment, CaseAssignment]:
        """
        获取指派列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
            lawyer_id: 律师 ID（可选，用于过滤）
            user: 当前用户

        Returns:
            指派查询集
        """
        qs = CaseAssignment.objects.select_related("case", "lawyer").order_by("-id")

        # 应用过滤条件
        if case_id:
            qs = qs.filter(case_id=case_id)
        if lawyer_id:
            qs = qs.filter(lawyer_id=lawyer_id)

        logger.debug(
            "获取指派列表",
            extra={
                "action": "list_assignments",
                "case_id": case_id,
                "lawyer_id": lawyer_id,
                "user_id": getattr(user, "id", None) if user else None,
                "count": "deferred",
            },
        )

        return qs

    def get_assignment(
        self,
        assignment_id: int,
        user: User | None = None,
    ) -> CaseAssignment:
        """
        获取单个指派

        Args:
            assignment_id: 指派 ID
            user: 当前用户

        Returns:
            指派对象

        Raises:
            NotFoundError: 指派不存在
        """
        try:
            assignment = CaseAssignment.objects.select_related("case", "lawyer").get(id=assignment_id)

            logger.debug(
                "获取指派成功",
                extra={
                    "action": "get_assignment",
                    "assignment_id": assignment_id,
                    "case_id": assignment.case_id,
                    "lawyer_id": assignment.lawyer_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )

            return cast(CaseAssignment, assignment)
        except CaseAssignment.DoesNotExist as e:
            logger.warning(
                "指派不存在",
                extra={
                    "action": "get_assignment",
                    "assignment_id": assignment_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message=_("指派不存在"),
                code="ASSIGNMENT_NOT_FOUND",
                errors={"assignment_id": f"ID 为 {assignment_id} 的指派不存在"},
            ) from e

    @transaction.atomic
    def create_assignment(
        self,
        case_id: int,
        lawyer_id: int,
        user: User | None = None,
    ) -> CaseAssignment:
        """
        创建指派

        Args:
            case_id: 案件 ID
            lawyer_id: 律师 ID
            user: 当前用户

        Returns:
            创建的指派对象

        Raises:
            NotFoundError: 案件不存在
            ConflictError: 指派已存在
            ValidationException: 数据验证失败
        """
        # 验证案件是否存在
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist as e:
            logger.warning(
                "创建指派失败：案件不存在",
                extra={
                    "action": "create_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            ) from e

        # 检查是否已存在相同的指派
        if CaseAssignment.objects.filter(case_id=case_id, lawyer_id=lawyer_id).exists():
            logger.warning(
                "创建指派失败：指派已存在",
                extra={
                    "action": "create_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise ConflictError(
                message=_("指派已存在"),
                code="ASSIGNMENT_ALREADY_EXISTS",
                errors={"assignment": f"案件 {case_id} 已指派给律师 {lawyer_id}"},
            )

        # 创建指派
        assignment = CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id)

        logger.info(
            "创建指派成功",
            extra={
                "action": "create_assignment",
                "assignment_id": assignment.id,
                "case_id": case_id,
                "lawyer_id": lawyer_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return assignment

    @transaction.atomic
    def update_assignment(
        self,
        assignment_id: int,
        data: dict[str, Any],
        user: User | None = None,
    ) -> CaseAssignment:
        """
        更新指派

        Args:
            assignment_id: 指派 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的指派对象

        Raises:
            NotFoundError: 指派不存在
            ValidationException: 数据验证失败
        """
        try:
            assignment = CaseAssignment.objects.select_related("case").get(id=assignment_id)
        except CaseAssignment.DoesNotExist as e:
            logger.warning(
                "更新指派失败：指派不存在",
                extra={
                    "action": "update_assignment",
                    "assignment_id": assignment_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message=_("指派不存在"),
                code="ASSIGNMENT_NOT_FOUND",
                errors={"assignment_id": f"ID 为 {assignment_id} 的指派不存在"},
            ) from e

        # 验证案件是否存在（如果更新了 case_id）
        case_id = data.get("case_id")
        if case_id and case_id != assignment.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist as e:
                raise NotFoundError(
                    message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
                ) from e

        # 检查重复指派（如果更新了 case_id 或 lawyer_id）
        new_case_id = data.get("case_id", assignment.case_id)
        new_lawyer_id = data.get("lawyer_id", assignment.lawyer_id)

        if (new_case_id != assignment.case_id or new_lawyer_id != assignment.lawyer_id) and (
            CaseAssignment.objects.filter(case_id=new_case_id, lawyer_id=new_lawyer_id)
            .exclude(id=assignment_id)
            .exists()
        ):
            raise ConflictError(
                message=_("指派已存在"),
                code="ASSIGNMENT_ALREADY_EXISTS",
                errors={"assignment": f"案件 {new_case_id} 已指派给律师 {new_lawyer_id}"},
            )

        # 更新指派
        for key, value in data.items():
            if hasattr(assignment, key):
                setattr(assignment, key, value)

        assignment.save()

        logger.info(
            "更新指派成功",
            extra={
                "action": "update_assignment",
                "assignment_id": assignment_id,
                "case_id": assignment.case_id,
                "lawyer_id": assignment.lawyer_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return assignment # type: ignore

    @transaction.atomic
    def delete_assignment(
        self,
        assignment_id: int,
        user: User | None = None,
    ) -> dict[str, bool]:
        """
        删除指派

        Args:
            assignment_id: 指派 ID
            user: 当前用户

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 指派不存在
        """
        try:
            assignment = CaseAssignment.objects.get(id=assignment_id)
        except CaseAssignment.DoesNotExist as e:
            logger.warning(
                "删除指派失败：指派不存在",
                extra={
                    "action": "delete_assignment",
                    "assignment_id": assignment_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message=_("指派不存在"),
                code="ASSIGNMENT_NOT_FOUND",
                errors={"assignment_id": f"ID 为 {assignment_id} 的指派不存在"},
            ) from e

        case_id = assignment.case_id
        lawyer_id = assignment.lawyer_id

        assignment.delete()

        logger.info(
            "删除指派成功",
            extra={
                "action": "delete_assignment",
                "assignment_id": assignment_id,
                "case_id": case_id,
                "lawyer_id": lawyer_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )

        return {"success": True}
