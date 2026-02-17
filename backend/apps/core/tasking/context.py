"""Module for context."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any


def get_current_request_id() -> str | None:
    import threading

    from apps.core.infrastructure.request_context import get_request_id

    return get_request_id(fallback_generate=False) or getattr(threading.current_thread(), "request_id", None)


def set_current_request_id(request_id: str | None) -> str | None:
    import threading

    from apps.core.infrastructure.request_context import clear_request_context, set_request_context

    if request_id:
        threading.current_thread().request_id = request_id  # type: ignore[attr-defined]
        set_request_context(request_id=request_id, trace_id=request_id)
        return request_id
    if hasattr(threading.current_thread(), "request_id"):
        with contextlib.suppress(Exception):
            delattr(threading.current_thread(), "request_id")
    clear_request_context()
    return None


@dataclass(frozen=True)
class TaskContext:
    request_id: str | None = None
    correlation_id: str | None = None
    task_name: str | None = None
    entity_id: str | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "task_name": self.task_name,
            "entity_id": self.entity_id,
            "extra": self.extra or {},
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> TaskContext:
        data = value or {}
        return cls(
            request_id=data.get("request_id"),
            correlation_id=data.get("correlation_id"),
            task_name=data.get("task_name"),
            entity_id=data.get("entity_id"),
            extra=data.get("extra") or {},
        )
