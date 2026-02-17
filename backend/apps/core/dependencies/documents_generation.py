"""Module for documents generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        IContractFolderBindingService,
        IContractGenerationService,
        IContractService,
        IGenerationTaskService,
        ISupplementaryAgreementGenerationService,
    )


def build_generation_task_service() -> IGenerationTaskService:
    from apps.documents.services.generation.generation_task_service import GenerationTaskService

    return cast(IGenerationTaskService, GenerationTaskService())


def build_contract_generation_service_with_deps(
    *,
    contract_service: IContractService,
    folder_binding_service: IContractFolderBindingService,
) -> IContractGenerationService:
    from apps.documents.services.generation.contract_generation_service import ContractGenerationService

    return cast(
        IContractGenerationService,
        ContractGenerationService(
            contract_service=contract_service,
            folder_binding_service=folder_binding_service,
        ),
    )


def build_contract_generation_service() -> IContractGenerationService:
    from apps.core.interfaces import ServiceLocator

    return build_contract_generation_service_with_deps(
        contract_service=ServiceLocator.get_contract_service(),
        folder_binding_service=ServiceLocator.get_contract_folder_binding_service(),
    )


def build_supplementary_agreement_generation_service_with_deps(
    *,
    contract_service: IContractService,
    folder_binding_service: IContractFolderBindingService,
) -> ISupplementaryAgreementGenerationService:
    from apps.documents.services.generation.supplementary_agreement_generation_service import (
        SupplementaryAgreementGenerationService,
    )

    return cast(
        ISupplementaryAgreementGenerationService,
        SupplementaryAgreementGenerationService(
            contract_service=contract_service,
            folder_binding_service=folder_binding_service,
        ),
    )


def build_supplementary_agreement_generation_service() -> ISupplementaryAgreementGenerationService:
    from apps.core.interfaces import ServiceLocator

    return build_supplementary_agreement_generation_service_with_deps(
        contract_service=ServiceLocator.get_contract_service(),
        folder_binding_service=ServiceLocator.get_contract_folder_binding_service(),
    )
