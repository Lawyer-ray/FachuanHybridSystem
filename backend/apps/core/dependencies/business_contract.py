"""Module for business contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        ICaseService,
        IContractAssignmentQueryService,
        IContractFolderBindingService,
        IContractPaymentService,
        IContractService,
        ILawyerService,
    )


def build_contract_query_service() -> IContractService:
    from apps.contracts.services.contract.contract_service import ContractService
    from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

    return ContractServiceAdapter(contract_service=ContractService())


def build_contract_service() -> IContractService:
    raise RuntimeError(
        "build_contract_service 已改为显式注入依赖.请在 ServiceLocator 的组合根处调用 build_contract_service_with_deps."
    )


def build_contract_service_with_deps(*, case_service: ICaseService, lawyer_service: ILawyerService) -> IContractService:
    from apps.contracts.services import ContractServiceAdapter
    from apps.contracts.services.contract.usecases.composition import build_contract_service

    contract_service = build_contract_service(case_service=case_service, lawyer_service=lawyer_service)
    return ContractServiceAdapter(contract_service=contract_service)


def build_contract_assignment_query_service() -> IContractAssignmentQueryService:
    from apps.contracts.services.assignment.contract_assignment_query_service import ContractAssignmentQueryService

    return ContractAssignmentQueryService()


def build_contract_payment_service() -> IContractPaymentService:
    from apps.contracts.services.payment.contract_payment_service import ContractPaymentService

    return ContractPaymentService()


def build_contract_folder_binding_service() -> IContractFolderBindingService:
    from apps.contracts.services.folder.folder_binding_service import FolderBindingService

    from .documents_query import build_document_template_binding_service

    return FolderBindingService(document_template_binding_service=build_document_template_binding_service())
