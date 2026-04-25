"""Calendar event provider registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CalendarEvent, CalendarEventProvider, provider_available
from .ics_provider import IcsFileProvider
from .ics_url_provider import IcsUrlProvider

if TYPE_CHECKING:
    pass

__all__ = [
    "CalendarEvent",
    "CalendarEventProvider",
    "IcsFileProvider",
    "IcsUrlProvider",
    "get_provider",
    "get_available_providers",
    "provider_available",
]

_PROVIDER_REGISTRY: dict[str, type[CalendarEventProvider]] = {
    "ics": IcsFileProvider,  # type: ignore[dict-item]
    "ics_url": IcsUrlProvider,  # type: ignore[dict-item]
}


def _lazy_registry() -> dict[str, type[CalendarEventProvider]]:
    """Return the provider registry, lazily loading platform-specific providers."""
    registry: dict[str, type[CalendarEventProvider]] = dict(_PROVIDER_REGISTRY)
    if provider_available("mac"):
        from .mac_provider import MacCalendarProvider

        registry["mac"] = MacCalendarProvider  # type: ignore[assignment]
    if provider_available("windows"):
        from .windows_provider import WindowsOutlookProvider

        registry["windows"] = WindowsOutlookProvider  # type: ignore[assignment]
    return registry


def get_provider(name: str) -> CalendarEventProvider:
    """Return a provider instance by name. Raises KeyError if not found."""
    registry = _lazy_registry()
    cls = registry.get(name)
    if cls is None:
        available = ", ".join(sorted(registry.keys()))
        raise KeyError(f"Unknown provider '{name}'. Available: {available}")
    return cls()


def get_available_providers() -> list[dict[str, str]]:
    """Return a list of currently available providers with labels."""
    result: list[dict[str, str]] = [
        {"name": "ics", "label": "上传 .ics 文件"},
        {"name": "ics_url", "label": "从 URL 导入/同步"},
    ]
    if provider_available("mac"):
        result.append({"name": "mac", "label": "同步 macOS 日历"})
    if provider_available("windows"):
        result.append({"name": "windows", "label": "同步 Outlook 日历"})
    return result
