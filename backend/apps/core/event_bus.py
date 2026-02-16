"""Module for event bus."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class EventBus:
    _handlers: ClassVar[dict[str, list[Callable[..., Any]]]] = {}

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable[..., Any]) -> None:
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []
        cls._handlers[event_type].append(handler)

    @classmethod
    def publish(cls, event_type: str, data: Any | None = None) -> None:
        handlers = cls._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.exception("操作失败")
                logging.getLogger("apps").error(f"Event handler error: {e}")

    @classmethod
    def clear(cls, event_type: str | None = None) -> None:
        if event_type:
            cls._handlers.pop(event_type, None)
        else:
            cls._handlers.clear()


class Events:
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_DELETED = "case.deleted"

    CONTRACT_CREATED = "contract.created"
    CONTRACT_UPDATED = "contract.updated"

    PAYMENT_CREATED = "payment.created"
    PAYMENT_UPDATED = "payment.updated"

    USER_TEAM_CHANGED = "user.team_changed"
    CASE_ACCESS_GRANTED = "case.access_granted"
    CASE_ACCESS_REVOKED = "case.access_revoked"
