"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain import ContractAccessPolicy
from ..contract_service import ContractService
from ..query import ContractQueryFacade, ContractQueryService

if TYPE_CHECKING:
    from apps.core.protocols import ICaseService, ILawyerService


def build_contract_service(*, case_service: ICaseService, lawyer_service: ILawyerService) -> ContractService:
    from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService

    query_service = ContractQueryService()
    access_policy = ContractAccessPolicy()
    query_facade = ContractQueryFacade(query_service=query_service, access_policy=access_policy)

    return ContractService(
        case_service=case_service,
        lawyer_assignment_service=LawyerAssignmentService(lawyer_service=lawyer_service),
        query_service=query_service,
        access_policy=access_policy,
        query_facade=query_facade,
    )
