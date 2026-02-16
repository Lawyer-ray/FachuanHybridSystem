"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_system_config_service() -> Any:
    return ServiceLocator.get_system_config_service()
