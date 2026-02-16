"""Business logic services."""

from __future__ import annotations

from apps.contracts.services.contract.contract_admin_mutation_service import (
    ContractAdminMutationService as _ImplContractAdminMutationService,
)
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException


class ContractAdminMutationService(_ImplContractAdminMutationService):
    pass


__all__: list[str] = ["ContractAdminMutationService"]
