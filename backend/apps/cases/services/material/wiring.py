"""Dependency injection wiring."""

from __future__ import annotations

from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.services.case.case_query_service import CaseQueryService

from .case_material_service import CaseMaterialService


def build_case_material_service() -> CaseMaterialService:
    return CaseMaterialService(case_service=CaseQueryService(access_policy=CaseAccessPolicy()))
