"""服务定位器重导出层"""

from __future__ import annotations

from apps.core.event_bus import EventBus
from apps.core.events import Events
from apps.core.service_locator import ServiceLocator

__all__ = ["ServiceLocator", "EventBus", "Events"]
