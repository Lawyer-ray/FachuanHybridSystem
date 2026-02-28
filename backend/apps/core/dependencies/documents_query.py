"""Module for documents query."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        IDocumentService,
        IDocumentTemplateBindingService,
        IEvidenceListPlaceholderService,
        IEvidenceQueryService,
        IPromptVersionService,
    )


def build_folder_template_service() -> None:
    from apps.documents.services.template.folder_service import FolderTemplateService
    from apps.documents.services.template.folder_template.command_service import FolderTemplateCommandService
    from apps.documents.services.template.folder_template.id_service import FolderTemplateIdService
    from apps.documents.services.template.folder_template.query_service import FolderTemplateQueryService
    from apps.documents.services.template.folder_template.repo import FolderTemplateRepo
    from apps.documents.services.template.folder_template.structure_rules import FolderTemplateStructureRules
    from apps.documents.services.template.folder_template.validation_service import FolderTemplateValidationService
    from apps.documents.usecases.folder_template.folder_template_usecases import FolderTemplateUsecases

    id_service = FolderTemplateIdService()
    repo = FolderTemplateRepo()
    validation_service = FolderTemplateValidationService()
    structure_rules = FolderTemplateStructureRules(id_service=id_service)
    command_service = FolderTemplateCommandService(
        repo=repo,
        validation_service=validation_service,
        structure_rules=structure_rules,
    )
    query_service = FolderTemplateQueryService(repo=repo, id_service=id_service)

    return FolderTemplateService(  # type: ignore[return-value]
        usecases=FolderTemplateUsecases(
            command_service=command_service,
            query_service=query_service,
            validation_service=validation_service,
            structure_rules=structure_rules,
        )
    )


def build_document_service() -> IDocumentService:
    from apps.documents.services.document_service_adapter import DocumentServiceAdapter

    return DocumentServiceAdapter()


def build_document_template_binding_service() -> IDocumentTemplateBindingService:
    from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService

    return DocumentTemplateBindingService()


def build_evidence_query_service() -> IEvidenceQueryService:
    from apps.evidence.services.evidence_query_service import EvidenceQueryService

    return EvidenceQueryService()


def build_evidence_list_placeholder_service() -> IEvidenceListPlaceholderService:
    from apps.evidence.services.evidence_list_placeholder_service import EvidenceListPlaceholderService

    return cast(IEvidenceListPlaceholderService, EvidenceListPlaceholderService())


def build_prompt_version_service() -> IPromptVersionService:
    from apps.documents.services.code_placeholders.adapter import PromptVersionServiceAdapter

    return PromptVersionServiceAdapter()
