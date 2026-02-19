"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction

from apps.cases.models import Case
from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException

if TYPE_CHECKING:
    from .case_service import CaseService

logger = logging.getLogger("apps.cases")


class CaseMutationService:
    def __init__(self, case_service: CaseService) -> None:
        self.case_service = case_service

    def create_case(
        self,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        if not perm_open_access and (not user or not getattr(user, "is_authenticated", False)):
            raise ForbiddenError("用户未认证")

        contract_id = data.get("contract_id")
        if contract_id:
            contract = self.case_service.contract_service.get_contract(contract_id)
            if not contract:
                raise ValidationException(
                    message="合同不存在",
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"无效的合同 ID: {contract_id}"},
                )

            if not self.case_service.contract_service.validate_contract_active(contract_id):
                raise ValidationException(
                    message="合同未激活", code="CONTRACT_INACTIVE", errors={"contract_id": "合同状态不是 active"}
                )

        current_stage = data.get("current_stage")
        if current_stage:
            case_type: Any | None = None
            rep_stages: Any | None = None
            if contract_id:
                contract = self.case_service.contract_service.get_contract(contract_id)
                if contract:
                    case_type = contract.case_type
                    rep_stages = contract.representation_stages

            data["current_stage"] = self.case_service._validate_stage(current_stage, case_type, rep_stages)

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

    def update_case(
        self,
        case_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        try:
            case = Case.objects.select_related("contract").get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None

        if not perm_open_access:
            if not user or not getattr(user, "is_authenticated", False):
                raise ForbiddenError("用户未认证")
            self.case_service.access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message="无权限访问此案件",
            )

        contract_id = data.get("contract_id")
        if contract_id:
            contract = self.case_service.contract_service.get_contract(contract_id)
            if not contract:
                raise ValidationException(
                    message="合同不存在",
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"无效的合同 ID: {contract_id}"},
                )

        current_stage = data.get("current_stage")
        if current_stage:
            case_type: Any | None = None
            rep_stages: Any | None = None

            check_contract_id = contract_id if contract_id else case.contract_id

            if check_contract_id:
                contract = self.case_service.contract_service.get_contract(check_contract_id)
                if contract:
                    case_type = contract.case_type
                    rep_stages = contract.representation_stages

            data["current_stage"] = self.case_service._validate_stage(current_stage, case_type, rep_stages)

        for key, value in data.items():
            setattr(case, key, value)

        case.save()

        logger.info(
            "更新案件成功",
            extra={"action": "update_case", "case_id": case_id, "user_id": getattr(user, "id", None) if user else None},
        )

        return case

    @transaction.atomic
    def delete_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None

        if not perm_open_access:
            if not user or not getattr(user, "is_authenticated", False):
                raise ForbiddenError("用户未认证")
            self.case_service.access_policy.ensure_access(
                case_id=case.id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=case,
                message="无权限访问此案件",
            )

        logger.info(
            "删除案件",
            extra={"action": "delete_case", "case_id": case_id, "user_id": getattr(user, "id", None) if user else None},
        )

        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE cases_case
                    SET contract_id = NULL
                    WHERE contract_id IS NOT NULL
                      AND contract_id NOT IN (SELECT id FROM contracts_contract)
                    """
                )

        case.delete()

    def unbind_cases_from_contract_internal(self, contract_id: int) -> int:
        return int(Case.objects.filter(contract_id=contract_id).update(contract=None))
