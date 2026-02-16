"""Module for clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def utc_now() -> datetime:
    return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class SystemUTCClock:
    def now(self) -> datetime:
        return utc_now()
