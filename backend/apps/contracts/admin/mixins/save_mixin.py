"""
Contract Admin - Save Mixin

保存和删除钩子方法.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractStatus
from apps.core.exceptions import BusinessException

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


def _get_contract_admin_action_service() -> Any:
    from apps.contracts.services.admin_actions.wiring import build_contract_admin_action_service

    return build_contract_admin_action_service()


class ContractSaveMixin:
    """合同 Admin 保存/删除钩子的 Mixin"""

    def save_model(self, request: Any, obj: Any, form: Any, change: bool) -> None:
        """
        保存合同模型,处理建档编号逻辑和状态联动

        在保存合同时,如果建档状态发生变化,调用 ContractAdminService
        处理建档编号的生成或恢复.
        如果合同状态变更为已结案/已归档,自动将关联案件结案.

        Requirements: 2.1, 2.2, 3.3, 3.4
        """
        # 记录旧状态（仅编辑时）
        old_status = None
        if change and obj.pk:
            old_status = Contract.objects.filter(pk=obj.pk).values_list("status", flat=True).first()

        # 先保存对象以确保有 ID
        super().save_model(request, obj, form, change)

        # 处理建档编号逻辑
        try:
            service = _get_contract_admin_service()
            filing_number = service.handle_contract_filing_change(contract_id=obj.id, is_filed=obj.is_filed)

            if filing_number:
                obj.filing_number = filing_number
                logger.info(
                    f"合同 {obj.id} 建档编号已处理: {filing_number}",
                    extra={
                        "contract_id": obj.id,
                        "filing_number": filing_number,
                        "is_filed": obj.is_filed,
                    },
                )
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error(
                f"处理合同 {obj.id} 建档编号失败: {e!s}",
                extra={"contract_id": obj.id},
                exc_info=True,
            )
            messages.error(request, _("处理建档编号失败: %(err)s") % {"err": e})

        # 合同状态变更联动：已结案/已归档 → 自动结案关联案件
        if change and old_status is not None:
            new_status = obj.status
            if (
                new_status in (ContractStatus.CLOSED, ContractStatus.ARCHIVED)
                and old_status not in (ContractStatus.CLOSED, ContractStatus.ARCHIVED)
            ):
                try:
                    from apps.core.interfaces import ServiceLocator

                    case_service = ServiceLocator.get_case_service()
                    closed_count = case_service.close_cases_by_contract_internal(obj.id)
                    if closed_count:
                        logger.info(
                            "Admin 保存: 合同 %s 状态 %s→%s，自动结案 %d 个关联案件",
                            obj.id,
                            old_status,
                            new_status,
                            closed_count,
                            extra={"contract_id": obj.id, "old_status": old_status, "new_status": new_status, "closed_case_count": closed_count},
                        )
                        messages.success(
                            request,
                            _("合同状态已变更，%(count)d 个关联案件已自动结案") % {"count": closed_count},
                        )
                except (BusinessException, RuntimeError, Exception) as e:
                    logger.error(
                        f"合同 {obj.id} 状态联动结案失败: {e!s}",
                        extra={"contract_id": obj.id},
                        exc_info=True,
                    )
                    messages.warning(request, _("关联案件自动结案失败: %(err)s") % {"err": e})

    def save_related(self, request: Any, form: Any, formsets: Any, change: bool) -> None:
        super().save_related(request, form, formsets, change)

        contract = form.instance
        if not getattr(contract, "id", None):
            return

        try:
            action_service = _get_contract_admin_action_service()
            action_service.sync_case_assignments_from_contract(contract.id, user=getattr(request, "user", None))
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error(
                f"同步合同 {contract.id} 关联案件的律师指派失败: {e!s}",
                extra={"contract_id": contract.id},
                exc_info=True,
            )
            messages.error(request, _("同步关联案件律师指派失败: %(err)s") % {"err": e})

    def delete_model(self, request: Any, obj: Any) -> None:
        super().delete_model(request, obj)

    def delete_queryset(self, request: Any, queryset: Any) -> None:
        super().delete_queryset(request, queryset)
