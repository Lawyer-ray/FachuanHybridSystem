"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.protocols import ILLMService


def get_llm_service() -> ILLMService:
    return ServiceLocator.get_llm_service()
