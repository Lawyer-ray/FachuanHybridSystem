"""Dependency injection wiring."""

from __future__ import annotations


from apps.cases.services.case.composition import build_case_service
from apps.core.interfaces import ServiceLocator

from .case_material_service import CaseMaterialService


def build_case_material_service() -> CaseMaterialService:
    contract_service = ServiceLocator.get_contract_query_service()
    case_service = build_case_service(contract_service=contract_service)
    return CaseMaterialService(case_service=case_service)
