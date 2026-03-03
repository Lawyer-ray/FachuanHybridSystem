"""案件命令服务 - 负责所有案件写操作（创建、更新、删除）。"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case
from apps.core.business_config import business_config
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.interfaces import IContractService
from apps.core.permissions import PermissionMixin
from apps.core.security.access_context import AccessContext

from .case_access_policy import CaseAccessPolicy
from .case_queryset import get_case_queryset

logger = logging.getLogger("apps.cases")


class CaseCommandService(PermissionMixin):
    """案件命令服务，封装所有案件写操作业务逻辑。"""

    def __init__(
        self,
        contract_service: IContractService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self._contract_service = contract_service
        self._access_policy = access_policy or CaseAccessPolicy()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _validate_stage(
        self,
        stage: str,
        case_type: str | None,
        representation_stages: list[str] | None = None,
    ) -> str:
        """验证案件阶段是否合法。"""
        if case_type and not business_config.is_stage_valid_for_case_type(stage, case_type):
            raise ValidationException(
                _("该案件类型不支持此阶段"),
                errors={"current_stage": str(_("阶段不适用于此案件类型"))},
            )
        if representation_stages and stage not in representation_stages:
            raise ValidationException(
                _("当前阶段必须属于代理阶段集合"),
                errors={"current_stage": str(_("阶段不在代理范围内"))},
            )
        return stage

    def _resolve_stage_from_contract(
        self,
        contract_id: int | None,
        stage: str,
    ) -> str:
        """根据合同解析并验证阶段。"""
        case_type: str | None = None
        rep_stages: list[str] | None = None
        if contract_id and self._contract_service:
            contract = self._contract_service.get_contract(contract_id)
            if contract:
                case_type = contract.case_type
                rep_stages = contract.representation_stages
        return self._validate_stage(stage, case_type, rep_stages)

    def _validate_contract(self, contract_id: int) -> None:
        """验证合同存在且处于激活状态。"""
        if not self._contract_service:
            return
        contract = self._contract_service.get_contract(contract_id)
        if not contract:
            raise ValidationException(
                message=_("合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": f"无效的合同 ID: {contract_id}"},
            )
        if not self._contract_service.validate_contract_active(contract_id):
            raise ValidationException(
                message=_("合同未激活"),
                code="CONTRACT_INACTIVE",
                errors={"contract_id": str(_("合同状态不是 active"))},
            )

    # ------------------------------------------------------------------
    # 公开命令方法
    # ------------------------------------------------------------------

    @transaction.atomic
    def create_case(
        self,
        data: dict[str, Any],
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        """创建案件。

        ForbiddenError: 用户未认证
        ValidationException: 合同无效或阶段不合法
        """
        ctx = AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        self.check_authenticated(ctx)  # type: ignore

        contract_id: int | None = data.get("contract_id")
        if contract_id:
            self._validate_contract(contract_id)

        current_stage: str | None = data.get("current_stage")
        if current_stage:
            data["current_stage"] = self._resolve_stage_from_contract(contract_id, current_stage)

        logger.info(
            "创建案件",
            extra={
                "action": "create_case",
                "case_name": data.get("name"),
                "contract_id": contract_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        return Case.objects.create(**data)

    @transaction.atomic
    def create_case_ctx(self, *, data: dict[str, Any], ctx: AccessContext) -> Case:
        """创建案件（AccessContext 版本）。"""
        return self.create_case(
            data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def update_case(
        self,
        case_id: int,
        data: dict[str, Any],
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        """更新案件。

        NotFoundError: 案件不存在
        ForbiddenError: 无权限
        ValidationException: 合同无效或阶段不合法
        """
        try:
            case = get_case_queryset().select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id}) from None

        ctx = AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        if not perm_open_access:
            self.check_authenticated(ctx)  # type: ignore
            self._access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message=_("无权限访问此案件"),
            )

        contract_id: int | None = data.get("contract_id")
        if contract_id and self._contract_service:
            contract = self._contract_service.get_contract(contract_id)
            if not contract:
                raise ValidationException(
                    message=_("合同不存在"),
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"无效的合同 ID: {contract_id}"},
                )

        current_stage: str | None = data.get("current_stage")
        if current_stage:
            check_contract_id = contract_id if contract_id else case.contract_id
            data["current_stage"] = self._resolve_stage_from_contract(check_contract_id, current_stage)

        for key, value in data.items():
            setattr(case, key, value)
        case.save()

        logger.info(
            "更新案件成功",
            extra={
                "action": "update_case",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        return case

    @transaction.atomic
    def update_case_ctx(self, *, case_id: int, data: dict[str, Any], ctx: AccessContext) -> Case:
        """更新案件（AccessContext 版本）。"""
        return self.update_case(
            case_id,
            data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def delete_case(
        self,
        case_id: int,
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        """删除案件。

        NotFoundError: 案件不存在
        ForbiddenError: 无权限
        """
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id}) from None

        ctx = AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        if not perm_open_access:
            self.check_authenticated(ctx)  # type: ignore
            self._access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message=_("无权限访问此案件"),
            )

        logger.info(
            "删除案件",
            extra={
                "action": "delete_case",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        from apps.cases.utils import fix_sqlite_orphan_contract_fk

        fix_sqlite_orphan_contract_fk()
        case.delete()

    @transaction.atomic
    def delete_case_ctx(self, *, case_id: int, ctx: AccessContext) -> None:
        """删除案件（AccessContext 版本）。"""
        return self.delete_case(
            case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def create_case_full(
        self,
        data: dict[str, Any],
        actor_id: int | None = None,
        user: Any | None = None,
    ) -> dict[str, Any]:
        """创建完整案件（包含当事人、指派、日志）。

        ValidationException: 数据验证失败
        ForbiddenError: 权限不足
        """
        from .workflows.case_full_create_workflow import CaseFullCreateWorkflow

        return CaseFullCreateWorkflow(case_service=self).run(data=data, actor_id=actor_id, user=user)

    # ------------------------------------------------------------------
    # Internal (cross-module) mutations
    # ------------------------------------------------------------------

    def unbind_cases_from_contract_internal(self, contract_id: int) -> int:
        return int(Case.objects.filter(contract_id=contract_id).update(contract=None))
