"""Dependency injection wiring."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_cause_court_query_service() -> Any:
    return ServiceLocator.get_cause_court_query_service()
