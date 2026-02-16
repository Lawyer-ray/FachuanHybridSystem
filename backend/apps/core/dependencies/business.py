"""Module for business."""

from __future__ import annotations

"""业务依赖聚合入口 — 按业务域拆分为子模块,此文件保留为 re-export 入口."""


from .business_case import (
    build_case_assignment_service,
    build_case_assignment_service_with_deps,
    build_case_chat_service,
    build_case_filing_number_service,
    build_case_log_service,
    build_case_material_service,
    build_case_number_service,
    build_case_search_service,
    build_case_service,
    build_case_service_with_deps,
    build_litigation_fee_calculator_service,
)
from .business_client import build_client_service
from .business_contract import (
    build_contract_assignment_query_service,
    build_contract_folder_binding_service,
    build_contract_payment_service,
    build_contract_query_service,
    build_contract_service,
    build_contract_service_with_deps,
)
from .business_organization import (
    build_lawfirm_service,
    build_lawyer_service,
    build_organization_service,
    build_reminder_service,
)

__all__: list[str] = [
    "build_case_assignment_service",
    "build_case_assignment_service_with_deps",
    "build_case_chat_service",
    "build_case_filing_number_service",
    "build_case_log_service",
    "build_case_material_service",
    "build_case_number_service",
    "build_case_search_service",
    "build_case_service",
    "build_case_service_with_deps",
    "build_client_service",
    "build_contract_assignment_query_service",
    "build_contract_folder_binding_service",
    "build_contract_payment_service",
    "build_contract_query_service",
    "build_contract_service",
    "build_contract_service_with_deps",
    "build_lawfirm_service",
    "build_lawyer_service",
    "build_litigation_fee_calculator_service",
    "build_organization_service",
    "build_reminder_service",
]
