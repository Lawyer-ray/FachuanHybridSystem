"""Module for events."""

from __future__ import annotations

from typing import Any

from .context import get_request_id
from .time import utc_now_iso


def build_event_extra(*, action: str, request_id: str | None = None, **fields: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {"action": action, "timestamp": utc_now_iso()}
    extra["request_id"] = request_id or get_request_id()
    for k, v in fields.items():
        if v is not None:
            extra[k] = v
    return extra
