"""Django admin configuration."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_contract_display_service() -> Any:
    from apps.contracts.services import ContractDisplayService

    if ServiceLocator._scope.get() is None:
        return ContractDisplayService()

    return ServiceLocator.get_or_create(
        "contracts.contract_display_service",
        lambda: ContractDisplayService(),
    )


def get_contract_progress_service() -> Any:
    from apps.contracts.services import ContractProgressService

    if ServiceLocator._scope.get() is None:
        return ContractProgressService()

    return ServiceLocator.get_or_create(
        "contracts.contract_progress_service",
        lambda: ContractProgressService(),
    )


def get_contract_admin_service() -> Any:
    from apps.contracts.services import ContractAdminService

    if ServiceLocator._scope.get() is None:
        return ContractAdminService(
            display_service=get_contract_display_service(),
            progress_service=get_contract_progress_service(),
        )

    return ServiceLocator.get_or_create(
        "contracts.contract_admin_service",
        lambda: ContractAdminService(
            display_service=get_contract_display_service(),
            progress_service=get_contract_progress_service(),
        ),
    )


def get_contract_batch_folder_binding_service() -> Any:
    from apps.contracts.services import ContractBatchFolderBindingService

    if ServiceLocator._scope.get() is None:
        return ContractBatchFolderBindingService()

    return ServiceLocator.get_or_create(
        "contracts.contract_batch_folder_binding_service",
        lambda: ContractBatchFolderBindingService(),
    )


def get_contract_folder_binding_service() -> Any:
    from apps.contracts.services import FolderBindingService
    from apps.core.dependencies.documents import build_document_template_binding_service

    if ServiceLocator._scope.get() is None:
        return FolderBindingService(document_template_binding_service=build_document_template_binding_service())

    return ServiceLocator.get_or_create(
        "contracts.folder_binding_service",
        lambda: FolderBindingService(document_template_binding_service=build_document_template_binding_service()),
    )


def get_contract_oa_sync_service() -> Any:
    from apps.contracts.services import ContractOASyncService

    if ServiceLocator._scope.get() is None:
        return ContractOASyncService()

    return ServiceLocator.get_or_create(
        "contracts.contract_oa_sync_service",
        lambda: ContractOASyncService(),
    )


def get_contract_mutation_facade() -> Any:
    from apps.contracts.services.contract.wiring import get_contract_mutation_facade as _get_contract_mutation_facade

    return _get_contract_mutation_facade()


def get_contract_admin_action_service() -> Any:
    from apps.contracts.services.admin_actions.wiring import build_contract_admin_action_service

    if ServiceLocator._scope.get() is None:
        return build_contract_admin_action_service()

    return ServiceLocator.get_or_create(
        "contracts.contract_admin_action_service",
        build_contract_admin_action_service,
    )


def get_contract_assignment_query_service() -> Any:
    from apps.contracts.services.assignment.contract_assignment_query_service import ContractAssignmentQueryService

    if ServiceLocator._scope.get() is None:
        return ContractAssignmentQueryService()

    return ServiceLocator.get_or_create(
        "contracts.contract_assignment_query_service",
        lambda: ContractAssignmentQueryService(),
    )


def get_material_service() -> Any:
    from apps.contracts.services.contract.integrations import MaterialService

    if ServiceLocator._scope.get() is None:
        return MaterialService()

    return ServiceLocator.get_or_create(
        "contracts.material_service",
        lambda: MaterialService(),
    )


def get_invoice_upload_service() -> Any:
    from apps.contracts.services.contract.integrations import InvoiceUploadService

    if ServiceLocator._scope.get() is None:
        return InvoiceUploadService()

    return ServiceLocator.get_or_create(
        "contracts.invoice_upload_service",
        lambda: InvoiceUploadService(),
    )
