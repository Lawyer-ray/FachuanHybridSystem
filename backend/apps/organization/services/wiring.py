"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ServiceLocator

from .access.org_access_computation_service import OrgAccessComputationService


def build_org_access_computation_service() -> OrgAccessComputationService:
    return OrgAccessComputationService(case_service=ServiceLocator.get_case_service())
