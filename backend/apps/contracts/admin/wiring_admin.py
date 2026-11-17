"""Django admin configuration.

admin 层只做「路由到工厂」：本模块**不出现任何 `XxxService(`**（四层架构禁令见
`docs/harness/backend/four-layer.md`）。每个 `get_xxx()` 的函数名与签名保持不变——测试有 11 处
patch 指向本模块的属性（`test_contract_add_deferred_folder_binding.py` 9 处、
`test_contract_http_smoke.py` 2 处）。

生命周期语义：全部走 `ServiceLocator.get_or_create(<原键>)`，与改造前「有 scope 时」的分支逐字一致；
改造前 `ServiceLocator._scope.get() is None` 时的新建分支已删除——`ServiceLocator._storage()` 在无 scope
时本就回落到进程级 `_services`，该分支是冗余噪音（详见 WS5 诊断报告 §4.1）。
"""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_contract_display_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.wiring import build_contract_display_service

    return ServiceLocator.get_or_create("contracts.contract_display_service", build_contract_display_service)


def get_contract_progress_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.wiring import build_contract_progress_service

    return ServiceLocator.get_or_create("contracts.contract_progress_service", build_contract_progress_service)


def get_contract_admin_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.wiring import build_contract_admin_service

    return ServiceLocator.get_or_create("contracts.contract_admin_service", build_contract_admin_service)


def get_contract_batch_folder_binding_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.integrations.wiring import build_contract_batch_folder_binding_service

    return ServiceLocator.get_or_create(
        "contracts.contract_batch_folder_binding_service",
        build_contract_batch_folder_binding_service,
    )


def get_contract_folder_binding_service() -> Any:  # pragma: no cover
    from apps.core.dependencies.business_contract import build_contract_folder_binding_service

    return ServiceLocator.get_or_create(
        "contracts.folder_binding_service",
        build_contract_folder_binding_service,
    )


def get_contract_oa_sync_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.integrations.wiring import build_contract_oa_sync_service

    return ServiceLocator.get_or_create("contracts.contract_oa_sync_service", build_contract_oa_sync_service)


def get_oa_party_resolution_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.integrations.wiring import build_oa_party_resolution_service

    return ServiceLocator.get_or_create("contracts.oa_party_resolution_service", build_oa_party_resolution_service)


def get_contract_mutation_facade() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.wiring import get_contract_mutation_facade as _get_contract_mutation_facade

    return _get_contract_mutation_facade()


def get_contract_admin_action_service() -> Any:  # pragma: no cover
    from apps.contracts.services.admin_actions.wiring import build_contract_admin_action_service

    return ServiceLocator.get_or_create(
        "contracts.contract_admin_action_service",
        build_contract_admin_action_service,
    )


def get_contract_assignment_query_service() -> Any:  # pragma: no cover
    from apps.core.dependencies.business_contract import build_contract_assignment_query_service

    return ServiceLocator.get_or_create(
        "contracts.contract_assignment_query_service",
        build_contract_assignment_query_service,
    )


def get_material_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.integrations.wiring import build_material_service

    return ServiceLocator.get_or_create("contracts.material_service", build_material_service)


def get_invoice_upload_service() -> Any:  # pragma: no cover
    from apps.contracts.services.contract.integrations.wiring import build_invoice_upload_service

    return ServiceLocator.get_or_create("contracts.invoice_upload_service", build_invoice_upload_service)


def get_client_payment_image_service() -> Any:  # pragma: no cover
    from apps.contracts.services.client_payment.wiring import build_client_payment_image_service

    return ServiceLocator.get_or_create("contracts.client_payment_image_service", build_client_payment_image_service)


def get_client_payment_record_service() -> Any:  # pragma: no cover
    from apps.contracts.services.client_payment.wiring import build_client_payment_record_service

    return ServiceLocator.get_or_create("contracts.client_payment_record_service", build_client_payment_record_service)


def get_script_executor_service() -> Any:  # pragma: no cover
    from apps.oa_filing.services.wiring import build_script_executor_service

    return ServiceLocator.get_or_create("oa_filing.script_executor_service", build_script_executor_service)
