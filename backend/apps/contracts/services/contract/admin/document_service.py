"""Business logic services."""

from __future__ import annotations

from apps.contracts.services.contract.contract_admin_document_service import (
    ContractAdminDocumentService as _ImplContractAdminDocumentService,
)
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException


class ContractAdminDocumentService(_ImplContractAdminDocumentService):
    pass


__all__: list[str] = ["ContractAdminDocumentService"]
