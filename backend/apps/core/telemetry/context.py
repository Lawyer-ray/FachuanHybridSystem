"""Module for context."""

from __future__ import annotations

from apps.core.infrastructure.request_context import get_request_id as _get_request_id


def get_request_id() -> str:
    return _get_request_id() or ""
