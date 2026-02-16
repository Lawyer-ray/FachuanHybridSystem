"""
Contract Admin - Save Mixin

保存和删除钩子方法.
"""

import logging
from typing import Any

from django.contrib import messages

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.services import ContractAdminService, ContractDisplayService

    display_service = ContractDisplayService()
    return ContractAdminService(display_service=display_service)


def _get_contract_admin_action_service() -> Any:
    from apps.contracts.services.admin_actions.wiring import build_contract_admin_action_service

    return build_contract_admin_action_service()


class ContractSaveMixin:
    """合同 Admin 保存/删除钩子的 Mixin"""

    def save_model(self, request, obj, form, change) -> None:
        """
        保存合同模型,处理建档编号逻辑

        在保存合同时,如果建档状态发生变化,调用 ContractAdminService
        处理建档编号的生成或恢复.

        Requirements: 2.1, 2.2, 3.3, 3.4
        """
        # 先保存对象以确保有 ID
        super().save_model(request, obj, form, change)

        # 处理建档编号逻辑
        try:
            service = _get_contract_admin_service()
            filing_number = service.handle_contract_filing_change(contract_id=obj.id, is_archived=obj.is_archived)

            if filing_number:
                obj.filing_number = filing_number
                logger.info(
                    f"合同 {obj.id} 建档编号已处理: {filing_number}",
                    extra={
                        "contract_id": obj.id,
                        "filing_number": filing_number,
                        "is_archived": obj.is_archived,
                    },
                )
        except Exception as e:
            logger.error(
                f"处理合同 {obj.id} 建档编号失败: {e!s}",
                extra={"contract_id": obj.id},
                exc_info=True,
            )
            messages.error(request, f"处理建档编号失败: {e!s}")

    def save_related(self, request, form, formsets, change) -> None:
        super().save_related(request, form, formsets, change)

        contract = form.instance
        if not getattr(contract, "id", None):
            return

        try:
            action_service = _get_contract_admin_action_service()
            action_service.sync_case_assignments_from_contract(contract.id, user=getattr(request, "user", None))
        except Exception as e:
            logger.error(
                f"同步合同 {contract.id} 关联案件的律师指派失败: {e!s}",
                extra={"contract_id": contract.id},
                exc_info=True,
            )
            messages.error(request, f"同步关联案件律师指派失败: {e!s}")

    def delete_model(self, request, obj) -> None:
        """
        删除合同前,先解除关联案件的引用

        由于 SQLite 的外键约束处理问题,即使使用 SET_NULL,
        在某些情况下仍会报 FOREIGN KEY constraint failed.
        因此在删除前手动将关联案件的 contract 字段设为 NULL.

        Requirements: 数据完整性
        """
        try:
            action_service = _get_contract_admin_action_service()
            case_count = action_service.unbind_cases_from_contract(obj.id)
            if case_count > 0:
                logger.info(
                    f"删除合同 {obj.id} 前,已解除 {case_count} 个关联案件的引用",
                    extra={"contract_id": obj.id, "case_count": case_count},
                )

            super().delete_model(request, obj)

        except Exception as e:
            logger.error(
                f"删除合同 {obj.id} 失败: {e!s}",
                extra={"contract_id": obj.id},
                exc_info=True,
            )
            messages.error(request, f"删除合同失败: {e!s}")
            raise

    def delete_queryset(self, request, queryset) -> None:
        """
        批量删除合同前,先解除关联案件的引用

        处理 Admin 列表页的批量删除操作.

        Requirements: 数据完整性
        """
        try:
            contract_ids = list(queryset.values_list("id", flat=True))

            action_service = _get_contract_admin_action_service()
            case_count = action_service.unbind_cases_from_contracts(contract_ids)
            if case_count > 0:
                logger.info(
                    f"批量删除 {len(contract_ids)} 个合同前,已解除 {case_count} 个关联案件的引用",
                    extra={"contract_ids": contract_ids, "case_count": case_count},
                )

            super().delete_queryset(request, queryset)

        except Exception as e:
            logger.error(f"批量删除合同失败: {e!s}", exc_info=True)
            messages.error(request, f"批量删除合同失败: {e!s}")
            raise
