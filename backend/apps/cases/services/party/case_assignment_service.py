"""Business logic services."""

from __future__ import annotations

"""
案件指派服务层
处理案件指派相关的业务逻辑
"""

import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.cases.models import Case, CaseAssignment
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ConflictError, NotFoundError
from apps.core.interfaces import ICaseService
from apps.core.protocols import IContractAssignmentQueryService
from apps.core.security import DjangoPermsMixin

logger = logging.getLogger("apps.cases")


class CaseAssignmentService(DjangoPermsMixin):
    """
    案件指派服务

    职责:
    1. 封装案件指派相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    """

    def __init__(
        self,
        case_service: ICaseService | None = None,
        contract_assignment_query_service: IContractAssignmentQueryService | None = None,
    ) -> None:
        """
        初始化服务(依赖注入)

        Args:
            case_service: 案件服务接口(注入)
        """
        self._case_service = case_service
        self._contract_assignment_query_service = contract_assignment_query_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载:优先使用注入实例"""
        if self._case_service is None:
            raise RuntimeError("CaseAssignmentService.case_service 未注入")
        return self._case_service

    @property
    def contract_assignment_query_service(self) -> IContractAssignmentQueryService:
        if self._contract_assignment_query_service is None:
            raise RuntimeError("CaseAssignmentService.contract_assignment_query_service 未注入")
        return self._contract_assignment_query_service

    def list_assignments(
        self,
        case_id: int | None = None,
        lawyer_id: int | None = None,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        """
        获取指派列表

        Args:
            case_id: 案件 ID(可选,用于过滤)
            lawyer_id: 律师 ID(可选,用于过滤)
            user: 当前用户

        Returns:
            指派查询集
        """
        self.ensure_admin(user, perm_open_access=perm_open_access)

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
                "count": qs.count(),
            },
        )

        return qs

    def get_assignment(
        self,
        assignment_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
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
        self.ensure_admin(user, perm_open_access=perm_open_access)

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
        except CaseAssignment.DoesNotExist:
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
            ) from None

    @transaction.atomic
    def create_assignment(
        self,
        case_id: int,
        lawyer_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
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
        self.ensure_admin(user, perm_open_access=perm_open_access)

        # 验证案件是否存在
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            logger.warning(
                "创建指派失败:案件不存在",
                extra={
                    "action": "create_assignment",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "user_id": getattr(user, "id", None) if user else None,
                },
            )
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            ) from None

        # 检查是否已存在相同的指派
        if CaseAssignment.objects.filter(case_id=case_id, lawyer_id=lawyer_id).exists():
            logger.warning(
                "创建指派失败:指派已存在",
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
        user: Any | None = None,
        perm_open_access: bool = False,
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
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            assignment = CaseAssignment.objects.select_related("case").get(id=assignment_id)
        except CaseAssignment.DoesNotExist:
            logger.warning(
                "更新指派失败:指派不存在",
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
            ) from None

        # 验证案件是否存在(如果更新了 case_id)
        case_id = data.get("case_id")
        if case_id and case_id != assignment.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist:
                raise NotFoundError(
                    message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
                ) from None

        # 检查重复指派(如果更新了 case_id 或 lawyer_id)
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

        return assignment

    @transaction.atomic
    def delete_assignment(
        self,
        assignment_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
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
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            assignment = CaseAssignment.objects.get(id=assignment_id)
        except CaseAssignment.DoesNotExist:
            logger.warning(
                "删除指派失败:指派不存在",
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
            ) from None

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

    @transaction.atomic
    def sync_assignments_from_contract(
        self,
        case_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, int]:
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            case = Case.objects.select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            ) from None

        contract_id = getattr(case, "contract_id", None)
        if not contract_id:
            return {"created": 0, "deleted": 0}

        lawyer_ids = self.contract_assignment_query_service.list_lawyer_ids_by_contract_internal(contract_id)

        deleted, _count = CaseAssignment.objects.filter(case_id=case_id).delete()
        if not lawyer_ids:
            return {"created": 0, "deleted": deleted}

        created = len(
            CaseAssignment.objects.bulk_create(
                [CaseAssignment(case_id=case_id, lawyer_id=lawyer_id) for lawyer_id in lawyer_ids]
            )
        )
        return {"created": created, "deleted": deleted}

    @transaction.atomic
    def create_assignment_internal(self, case_id: int, lawyer_id: int) -> bool:
        try:
            case = Case.objects.get(id=case_id)

            if CaseAssignment.objects.filter(case_id=case_id, lawyer_id=lawyer_id).exists():
                logger.warning(
                    "案件指派已存在",
                    extra={
                        "action": "create_assignment_internal",
                        "case_id": case_id,
                        "lawyer_id": lawyer_id,
                        "status": "already_exists",
                    },
                )
                return True

            CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id)
            logger.info(
                "创建案件指派成功",
                extra={"action": "create_assignment_internal", "case_id": case_id, "lawyer_id": lawyer_id},
            )
            return True
        except Case.DoesNotExist:
            logger.error(
                "创建案件指派失败:案件不存在",
                extra={
                    "action": "create_assignment_internal",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "error": "case_not_found",
                },
            )
            return False
        except Exception as e:
            logger.error(
                f"创建案件指派失败:{e}",
                extra={
                    "action": "create_assignment_internal",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "error": str(e),
                },
            )
            return False
