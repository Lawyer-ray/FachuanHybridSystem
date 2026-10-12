"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.cases.models import Case, CaseAssignment, CaseAssignmentSource
from apps.cases.schemas.assignment_schemas import CaseAssignmentUpdate
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

            case_id: 案件 ID(可选,用于过滤)
            lawyer_id: 律师 ID(可选,用于过滤)
            user: 当前用户

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
                "count": "deferred",
            },
        )

        return qs  # type: ignore[return-value]

    def get_assignment(
        self,
        assignment_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> CaseAssignment:
        """
        获取单个指派

            assignment_id: 指派 ID
            user: 当前用户

            指派对象

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

            return assignment
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
                message="指派不存在",
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
    ) -> CaseAssignment:  # pragma: no cover
        """
        创建指派

            case_id: 案件 ID
            lawyer_id: 律师 ID
            user: 当前用户

            创建的指派对象

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
                message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
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
                message="指派已存在",
                code="ASSIGNMENT_ALREADY_EXISTS",
                errors={"assignment": f"案件 {case_id} 已指派给律师 {lawyer_id}"},
            )

        # 创建指派
        assignment = CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id, source=CaseAssignmentSource.MANUAL)

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
    ) -> CaseAssignment:  # pragma: no cover
        """
        更新指派

            assignment_id: 指派 ID
            data: 更新数据
            user: 当前用户

            更新后的指派对象

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
                message="指派不存在",
                code="ASSIGNMENT_NOT_FOUND",
                errors={"assignment_id": f"ID 为 {assignment_id} 的指派不存在"},
            ) from None
        original_lawyer_id = assignment.lawyer_id

        # 验证案件是否存在(如果更新了 case_id)
        case_id = data.get("case_id")
        if case_id and case_id != assignment.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist:
                raise NotFoundError(
                    message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
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
                message="指派已存在",
                code="ASSIGNMENT_ALREADY_EXISTS",
                errors={"assignment": f"案件 {new_case_id} 已指派给律师 {new_lawyer_id}"},
            )

        # 更新指派
        allowed_keys = CaseAssignmentUpdate.model_fields.keys()
        for key, value in data.items():
            if key in allowed_keys:
                setattr(assignment, key, value)

        # 手动改派（换了律师）视为手动添加，脱离合同同步的清理范围
        if assignment.lawyer_id != original_lawyer_id:
            assignment.source = CaseAssignmentSource.MANUAL

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

            assignment_id: 指派 ID
            user: 当前用户

            {"success": True}

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
                message="指派不存在",
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
    ) -> dict[str, int]:  # pragma: no cover
        """按合同指派 diff 同步案件指派。

        只管理 source=contract 的行：
        - 合同上已移除的律师 → 删除对应的 contract 行；
        - 合同上新出现的律师 → 补建 contract 行；
        source=manual 的行（案件级手动添加/改派）任何情况下不删除、不覆盖。
        """
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            case = Case.objects.select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            ) from None

        contract_id = getattr(case, "contract_id", None)
        if not contract_id:
            return {"created": 0, "deleted": 0}

        contract_lawyer_ids = {
            lawyer_id
            for lawyer_id in self.contract_assignment_query_service.list_lawyer_ids_by_contract_internal(contract_id)
            if lawyer_id is not None
        }

        existing_rows = CaseAssignment.objects.filter(case_id=case_id).only("id", "lawyer_id", "source")
        existing_by_lawyer = {row.lawyer_id: row for row in existing_rows}

        stale_contract_ids = [
            row.id
            for lawyer_id, row in existing_by_lawyer.items()
            if row.source == CaseAssignmentSource.CONTRACT and lawyer_id not in contract_lawyer_ids
        ]

        to_create = [
            CaseAssignment(case_id=case_id, lawyer_id=lawyer_id, source=CaseAssignmentSource.CONTRACT)
            for lawyer_id in sorted(contract_lawyer_ids - set(existing_by_lawyer))
        ]

        deleted = 0
        if stale_contract_ids:
            deleted, _count = CaseAssignment.objects.filter(id__in=stale_contract_ids).delete()
        created = len(CaseAssignment.objects.bulk_create(to_create)) if to_create else 0

        if created or deleted:
            logger.info(
                "按合同 diff 同步案件指派",
                extra={
                    "action": "sync_assignments_from_contract",
                    "case_id": case_id,
                    "contract_id": contract_id,
                    # created/deleted 是 LogRecord 保留属性，extra 里必须用 _count 后缀
                    "created_count": created,
                    "deleted_count": deleted,
                },
            )
        return {"created": created, "deleted": deleted}

    @transaction.atomic
    def create_assignment_internal(self, case_id: int, lawyer_id: int) -> bool:  # pragma: no cover
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

            # 仅由「从合同生成案件」流程调用，指派来自合同 → 标记 contract 来源，纳入后续同步管理
            CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id, source=CaseAssignmentSource.CONTRACT)
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
                "创建案件指派失败: %s",
                e,
                extra={
                    "action": "create_assignment_internal",
                    "case_id": case_id,
                    "lawyer_id": lawyer_id,
                    "error": str(e),
                },
            )
            return False
