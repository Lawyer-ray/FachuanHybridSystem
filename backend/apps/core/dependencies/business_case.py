"""Module for business case."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        ICaseAssignmentService,
        ICaseChatService,
        ICaseFilingNumberService,
        ICaseLogService,
        ICaseMaterialService,
        ICaseNumberService,
        ICaseSearchService,
        ICaseService,
        IClientService,
        IContractAssignmentQueryService,
        IContractService,
        ILitigationFeeCalculatorService,
    )


def build_case_service() -> ICaseService:
    raise RuntimeError(
        "build_case_service 已改为显式注入依赖.请在 ServiceLocator 的组合根处调用 build_case_service_with_deps."
    )


def build_case_service_with_deps(*, contract_service: IContractService, client_service: IClientService) -> ICaseService:
    from apps.cases.services.case.case_service_adapter import CaseServiceAdapter

    return CaseServiceAdapter(contract_service=contract_service, client_service=client_service)


def build_case_assignment_service() -> None:
    raise RuntimeError(
        "build_case_assignment_service 已改为显式注入依赖."
        "请在 ServiceLocator 的组合根处调用 build_case_assignment_service_with_deps."
    )


def build_case_assignment_service_with_deps(
    *,
    case_service: ICaseService,
    contract_assignment_query_service: IContractAssignmentQueryService,
) -> ICaseAssignmentService:
    from apps.cases.services import CaseAssignmentService

    service = CaseAssignmentService(
        case_service=case_service,
        contract_assignment_query_service=contract_assignment_query_service,
    )
    return cast("ICaseAssignmentService", service)


def build_case_material_service() -> ICaseMaterialService:
    from apps.cases.services.material.wiring import build_case_material_service

    return build_case_material_service()


def build_litigation_fee_calculator_service() -> ILitigationFeeCalculatorService:
    from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

    return LitigationFeeCalculatorService()


def build_case_filing_number_service() -> ICaseFilingNumberService:
    from apps.cases.services.number.case_filing_number_service_adapter import CaseFilingNumberServiceAdapter

    return CaseFilingNumberServiceAdapter()


def build_case_chat_service() -> ICaseChatService:
    from apps.cases.services.chat.case_chat_service_adapter import CaseChatServiceAdapter

    return CaseChatServiceAdapter()


def build_case_number_service() -> ICaseNumberService:
    from apps.cases.services.number.case_number_service_adapter import CaseNumberServiceAdapter

    return CaseNumberServiceAdapter()


def build_case_search_service() -> ICaseSearchService:
    from apps.cases.services.case_search_service_adapter import CaseSearchServiceAdapter

    return CaseSearchServiceAdapter()


def build_case_log_service() -> ICaseLogService:
    from apps.cases.services.log.caselog_service_adapter import CaseLogServiceAdapter

    return CaseLogServiceAdapter()
