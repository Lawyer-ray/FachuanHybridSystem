"""Module for automation insurance."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.protocols import IPreservationQuoteService


def build_preservation_quote_service() -> IPreservationQuoteService:
    from plugins.court_automation.preservation_quote.service_adapter import PreservationQuoteServiceAdapter

    return PreservationQuoteServiceAdapter()
