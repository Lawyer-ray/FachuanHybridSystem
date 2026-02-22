"""Business logic services."""

from __future__ import annotations

from apps.core.interfaces import IContractService

from .case_service import CaseService


def build_case_service(*, contract_service: IContractService) -> CaseService:
    return CaseService(contract_service=contract_service)
