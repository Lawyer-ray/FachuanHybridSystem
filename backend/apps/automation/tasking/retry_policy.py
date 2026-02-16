"""Module for retry policy."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


class ExponentialBackoffRetryPolicy:
    def __init__(self, *, base_seconds: int = 60, max_seconds: int = 3600) -> None:
        self.base_seconds = base_seconds
        self.max_seconds = max_seconds

    def compute_delay_seconds(self, *, retry_count: int) -> int:
        if retry_count <= 0:
            return self.base_seconds
        return min((2 ** (retry_count - 1)) * self.base_seconds, self.max_seconds)  # type: ignore[no-any-return]

    def next_run_time(self, *, retry_count: int) -> None:
        delay_seconds = self.compute_delay_seconds(retry_count=retry_count)
        return timezone.now() + timedelta(seconds=delay_seconds), delay_seconds  # type: ignore[return-value]
