"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ICaseService, ServiceLocator


def get_case_service() -> ICaseService:
    return ServiceLocator.get_case_service()
