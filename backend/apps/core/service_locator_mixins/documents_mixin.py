"""Module for documents mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .automation_mixin import _ServiceLocatorStub

if TYPE_CHECKING:
    from apps.core.protocols import (
        IContractGenerationService,
        IDocumentService,
        IDocumentTemplateBindingService,
        IEvidenceListPlaceholderService,
        IEvidenceQueryService,
        IGenerationTaskService,
        ISupplementaryAgreementGenerationService,
    )


class DocumentsServiceLocatorMixin(_ServiceLocatorStub):
    @classmethod
    def get_evidence_service(cls) -> Any:
        from apps.evidence.services.evidence_service import EvidenceService

        return cls.get_or_create("evidence_service", lambda: EvidenceService(case_service=cls.get_case_service()))

    @classmethod
    def get_file_storage(cls) -> Any:
        from apps.evidence.services.evidence_storage import evidence_file_storage

        return cls.get_or_create("file_storage", lambda: evidence_file_storage)

    @classmethod
    def get_document_service(cls) -> IDocumentService:
        from apps.core.dependencies import build_document_service

        return cls.get_or_create("document_service", build_document_service)

    @classmethod
    def get_document_template_binding_service(cls) -> IDocumentTemplateBindingService:
        from apps.core.dependencies import build_document_template_binding_service

        return cls.get_or_create("document_template_binding_service", build_document_template_binding_service)

    @classmethod
    def get_evidence_query_service(cls) -> IEvidenceQueryService:
        from apps.core.dependencies import build_evidence_query_service

        return cls.get_or_create("evidence_query_service", build_evidence_query_service)

    @classmethod
    def get_generation_task_service(cls) -> IGenerationTaskService:
        from apps.core.dependencies import build_generation_task_service

        return cls.get_or_create("generation_task_service", build_generation_task_service)

    @classmethod
    def get_evidence_list_placeholder_service(cls) -> IEvidenceListPlaceholderService:
        from apps.core.dependencies import build_evidence_list_placeholder_service

        return cls.get_or_create("evidence_list_placeholder_service", build_evidence_list_placeholder_service)

    @classmethod
    def get_contract_generation_service(cls) -> IContractGenerationService:
        from apps.core.dependencies import build_contract_generation_service_with_deps

        return cls.get_or_create(
            "contract_generation_service",
            lambda: build_contract_generation_service_with_deps(
                contract_service=cls.get_contract_service(),
                folder_binding_service=cls.get_contract_folder_binding_service(),
            ),
        )

    @classmethod
    def get_supplementary_agreement_generation_service(cls) -> ISupplementaryAgreementGenerationService:
        from apps.core.dependencies import build_supplementary_agreement_generation_service_with_deps

        return cls.get_or_create(
            "supplementary_agreement_generation_service",
            lambda: build_supplementary_agreement_generation_service_with_deps(
                contract_service=cls.get_contract_service(),
                folder_binding_service=cls.get_contract_folder_binding_service(),
            ),
        )

    @classmethod
    def get_folder_generation_service(cls) -> Any:
        from apps.core.dependencies import build_contract_folder_binding_service, build_contract_query_service
        from apps.documents.services.generation.folder_generation_service import FolderGenerationService

        return cls.get_or_create(
            "folder_generation_service",
            lambda: FolderGenerationService(
                contract_service=cls.get_contract_service(),
                folder_binding_service=cls.get_contract_folder_binding_service(),
            ),
        )
