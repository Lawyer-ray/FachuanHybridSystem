"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import (
    ICaseFilingNumberService,
    ICaseService,
    IDocumentService,
    IOrganizationService,
    IReminderService,
    ServiceLocator,
)


def get_case_service() -> ICaseService:
    return ServiceLocator.get_case_service()


def get_document_service() -> IDocumentService:
    return ServiceLocator.get_document_service()


def get_case_filing_number_service() -> ICaseFilingNumberService:
    return ServiceLocator.get_case_filing_number_service()


def get_organization_service() -> IOrganizationService:
    return ServiceLocator.get_organization_service()


def get_reminder_service() -> IReminderService:
    return ServiceLocator.get_reminder_service()
