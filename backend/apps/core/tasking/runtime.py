"""Module for runtime."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskRunContext:
    started_monotonic: float
    soft_deadline_monotonic: float
    timeout_seconds: float

    @classmethod
    def from_django_q(
        cls,
        *,
        timeout_seconds: float | None = None,
        safety_margin_seconds: float = 30.0,
        min_soft_deadline_seconds: float = 60.0,
    ) -> TaskRunContext:
        start = time.monotonic()
        q_cluster = getattr(settings, "Q_CLUSTER", {}) or {}
        effective_timeout = timeout_seconds
        if effective_timeout is None:
            try:
                effective_timeout = float(q_cluster.get("timeout") or 600)
            except (TypeError, ValueError, KeyError):
                effective_timeout = 600.0
        soft = start + max(min_soft_deadline_seconds, float(effective_timeout) - float(safety_margin_seconds))
        return cls(started_monotonic=start, soft_deadline_monotonic=soft, timeout_seconds=float(effective_timeout))

    def is_past_soft_deadline(self) -> bool:
        return time.monotonic() > float(self.soft_deadline_monotonic)


class CancellationToken:
    def __init__(self, should_cancel: Callable[[], bool]) -> None:
        self._should_cancel = should_cancel

    def is_cancelled(self) -> bool:
        try:
            return bool(self._should_cancel())
        except (TypeError, AttributeError):
            return False


class ProgressReporter:
    def __init__(
        self,
        *,
        update_fn: Callable[[int, int, int, str], None],
        min_interval_seconds: float = 0.5,
    ) -> None:
        self._update_fn = update_fn
        self._min_interval_seconds = float(min_interval_seconds)
        self._last_update_ts = 0.0
        self._last_progress: int | None = None
        self._last_message: str | None = None

    def report(self, *, current: int, total: int, message: str, force: bool = False) -> None:
        try:
            progress = int(current * 100 / total) if total else 0
        except (ZeroDivisionError, TypeError, ValueError):
            progress = 0
        progress = min(max(progress, 0), 100)

        now_ts = time.time()
        if not force:
            if self._last_progress == progress and self._last_message == message:
                if now_ts - self._last_update_ts < self._min_interval_seconds:
                    return
            elif now_ts - self._last_update_ts < self._min_interval_seconds:
                return

        self._update_fn(progress, int(current), int(total), str(message or ""))
        self._last_update_ts = now_ts
        self._last_progress = progress
        self._last_message = message

    def report_extra(self, *, progress: int, current: int, total: int, message: str, force: bool = False) -> None:
        now_ts = time.time()
        if not force and now_ts - self._last_update_ts < self._min_interval_seconds:
            return
        self._update_fn(int(progress), int(current), int(total), str(message or ""))
        self._last_update_ts = now_ts
        self._last_progress = int(progress)
        self._last_message = message
