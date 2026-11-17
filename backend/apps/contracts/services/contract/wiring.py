"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.protocols import ICaseService, ILawyerService


def build_contract_service(*, case_service: ICaseService, lawyer_service: ILawyerService) -> Any:
    from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService

    from .contract_service import ContractService
    from .domain import ContractAccessPolicy
    from .query import ContractQueryFacade, ContractQueryService

    query_service = ContractQueryService()
    access_policy = ContractAccessPolicy()
    query_facade = ContractQueryFacade(query_service=query_service, access_policy=access_policy)

    return ContractService(
        case_service=case_service,
        lawyer_assignment_service=LawyerAssignmentService(lawyer_service=lawyer_service),
        query_service=query_service,
        access_policy=access_policy,
        query_facade=query_facade,
    )


def build_contract_display_service() -> Any:
    """构建合同显示服务实例（无状态，可安全缓存）。"""
    from .query import ContractDisplayService

    return ContractDisplayService()


def build_contract_progress_service() -> Any:
    """构建合同进度服务实例（无状态，可安全缓存）。"""
    from .query import ContractProgressService

    return ContractProgressService()


def build_contract_admin_service() -> Any:
    """构建合同 Admin 服务实例，注入显示 / 进度两个协作者。"""
    from .admin import ContractAdminService

    return ContractAdminService(
        display_service=build_contract_display_service(),
        progress_service=build_contract_progress_service(),
    )


def get_contract_service() -> Any:
    return ServiceLocator.get_contract_service()


def get_contract_domain_service() -> Any:
    return get_contract_service().contract_service


def get_contract_mutation_facade() -> Any:
    return get_contract_domain_service().mutation_facade


def get_contract_query_facade() -> Any:
    return get_contract_domain_service().query_facade


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_reminder_service() -> Any:
    return ServiceLocator.get_reminder_service()


def get_contract_generation_service() -> Any:
    return ServiceLocator.get_contract_generation_service()


def get_supplementary_agreement_generation_service() -> Any:
    return ServiceLocator.get_supplementary_agreement_generation_service()


def get_contract_folder_binding_service() -> Any:
    return ServiceLocator.get_contract_folder_binding_service()


def get_document_service() -> Any:
    return ServiceLocator.get_document_service()
