"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_client_service() -> Any:
    return ServiceLocator.get_client_service()


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_document_service() -> Any:
    return ServiceLocator.get_document_service()


def get_case_template_binding_service() -> Any:
    from .case_template_binding_service import CaseTemplateBindingService
    from .repo import CaseTemplateBindingRepo

    return CaseTemplateBindingService(document_service=get_document_service(), repo=CaseTemplateBindingRepo())


def get_case_document_template_admin_service() -> Any:
    from .case_document_template_admin_service import CaseDocumentTemplateAdminService
    from .repo import CaseTemplateBindingRepo

    return CaseDocumentTemplateAdminService(
        document_service=get_document_service(),
        binding_service=get_case_template_binding_service(),
        repo=CaseTemplateBindingRepo(),
    )
