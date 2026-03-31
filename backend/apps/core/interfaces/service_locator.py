"""服务定位器重导出层"""

from __future__ import annotations

from apps.core.infrastructure.event_bus import EventBus
from apps.core.infrastructure.events import Events
from apps.core.infrastructure.service_locator import ServiceLocator

__all__ = ["ServiceLocator", "EventBus", "Events"]
