"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ISystemConfigService, ServiceLocator


def get_system_config_service() -> ISystemConfigService:
    return ServiceLocator.get_system_config_service()
