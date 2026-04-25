"""Base types for calendar event providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class CalendarEvent:
    """Unified representation of a calendar event from any source."""

    uid: str = ""
    title: str = ""
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    location: str = ""
    description: str = ""
    organizer: str = ""
    calendar_name: str = ""
    is_all_day: bool = False
    raw: dict = field(default_factory=dict)


@runtime_checkable
class CalendarEventProvider(Protocol):
    """Protocol for calendar event providers."""

    def fetch_events(self, **kwargs: object) -> list[CalendarEvent]:
        """Fetch calendar events from the provider."""
        ...


def provider_available(name: str) -> bool:
    """Check whether a platform-specific provider is available."""
    if name == "mac":
        import platform

        if platform.system() != "Darwin":
            return False
        # Check osascript is available (always present on macOS)
        import shutil

        return shutil.which("osascript") is not None
    if name == "windows":
        try:
            import win32com.client

            return True
        except ImportError:
            return False
    return False
