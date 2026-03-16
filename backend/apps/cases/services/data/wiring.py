"""Dependency injection wiring."""

from __future__ import annotations

from apps.core.interfaces import ICauseCourtQueryService, ServiceLocator


def get_cause_court_query_service() -> ICauseCourtQueryService:
    return ServiceLocator.get_cause_court_query_service()
