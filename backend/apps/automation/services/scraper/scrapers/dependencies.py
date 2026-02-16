"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScraperDependencies:
    browser_service: Any
    captcha_service: Any
    validator: Any
    security: Any
    monitor: Any
    anti_detection: Any
