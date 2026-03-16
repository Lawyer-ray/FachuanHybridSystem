"""Lightweight compatibility event bus."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    """In-process event bus used by legacy checkpoints."""

    _handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)

    @classmethod
    def subscribe(cls, event_name: str, handler: Callable[[dict[str, Any]], None]) -> None:
        cls._handlers[event_name].append(handler)

    @classmethod
    def publish(cls, event_name: str, payload: dict[str, Any] | None = None) -> None:
        for handler in cls._handlers.get(event_name, []):
            handler(payload or {})
