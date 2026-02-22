"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ServiceLocator
from apps.core.protocols import ICaseAssignmentService, ICaseService

from .contract_admin_action_service import ContractAdminActionService


def get_case_service() -> ICaseService:
    return ServiceLocator.get_case_service()


def get_case_assignment_service() -> ICaseAssignmentService:
    return ServiceLocator.get_case_assignment_service()


def build_contract_admin_action_service() -> ContractAdminActionService:
    return ContractAdminActionService(
        case_service=get_case_service(),
        case_assignment_service=get_case_assignment_service(),
    )
