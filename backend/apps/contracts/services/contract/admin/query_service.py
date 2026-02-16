"""Business logic services."""

from __future__ import annotations

from apps.contracts.services.contract.contract_admin_query_service import (
    ContractAdminQueryService as _ImplContractAdminQueryService,
)
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException


class ContractAdminQueryService(_ImplContractAdminQueryService):
    pass


__all__: list[str] = ["ContractAdminQueryService"]
