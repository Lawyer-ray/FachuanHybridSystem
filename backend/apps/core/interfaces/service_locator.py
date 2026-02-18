"""
服务定位器和事件总线 - 重导出层
从 apps.core.service_locator 和 apps.core.event_bus 重导出
"""

from __future__ import annotations

from apps.core.event_bus import EventBus, Events
from apps.core.service_locator import ServiceLocator

__all__ = ["ServiceLocator", "EventBus", "Events"]
