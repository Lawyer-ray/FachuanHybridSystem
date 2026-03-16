"""Compatibility module for legacy case service import paths."""

from apps.cases.services import CaseService as _CaseService


class CaseService(_CaseService):
    """Backward-compatible CaseService symbol."""


__all__ = ["CaseService"]
