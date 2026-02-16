"""Module for notifications."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ConfigChangeListener(ABC):
    @abstractmethod
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None: ...

    def on_config_added(self, key: str, value: Any) -> None: ...

    def on_config_removed(self, key: str, old_value: Any) -> None: ...

    def on_config_reloaded(self) -> None: ...


@dataclass
class ConfigChangeEvent:
    key: str
    old_value: Any
    new_value: Any
    change_type: str
    timestamp: float = field(default_factory=time.time)


class ConfigNotificationManager:
    def __init__(self) -> None:
        self._listeners: list[ConfigChangeListener] = []
        self._key_listeners: dict[str, list[ConfigChangeListener]] = {}
        self._prefix_listeners: dict[str, list[ConfigChangeListener]] = {}
        self._event_history: list[ConfigChangeEvent] = []
        self._max_history = 100
        self._lock = threading.Lock()

    def add_listener(
        self, listener: ConfigChangeListener, key_filter: str | None = None, prefix_filter: str | None = None
    ) -> None:
        with self._lock:
            if key_filter:
                self._key_listeners.setdefault(key_filter, [])
                if listener not in self._key_listeners[key_filter]:
                    self._key_listeners[key_filter].append(listener)
            elif prefix_filter:
                self._prefix_listeners.setdefault(prefix_filter, [])
                if listener not in self._prefix_listeners[prefix_filter]:
                    self._prefix_listeners[prefix_filter].append(listener)
            else:
                if listener not in self._listeners:
                    self._listeners.append(listener)

    def remove_listener(self, listener: ConfigChangeListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

            for key_listeners in self._key_listeners.values():
                if listener in key_listeners:
                    key_listeners.remove(listener)

            for prefix_listeners in self._prefix_listeners.values():
                if listener in prefix_listeners:
                    prefix_listeners.remove(listener)

    def notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        change_type = self._determine_change_type(old_value, new_value)
        event = ConfigChangeEvent(key, old_value, new_value, change_type)

        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
            listeners_to_notify = self._collect_listeners(key)

        for listener in listeners_to_notify:
            self._dispatch_to_listener(listener, change_type, key, old_value, new_value)

    @staticmethod
    def _determine_change_type(old_value: Any, new_value: Any) -> str:
        if old_value is None and new_value is not None:
            return "added"
        if old_value is not None and new_value is None:
            return "removed"
        return "modified"

    def _collect_listeners(self, key: str) -> set[Any]:
        listeners: set[ConfigChangeListener] = set()
        listeners.update(self._listeners)
        if key in self._key_listeners:
            listeners.update(self._key_listeners[key])
        for prefix, prefix_listeners in self._prefix_listeners.items():
            if key.startswith(prefix):
                listeners.update(prefix_listeners)
        return listeners

    @staticmethod
    def _dispatch_to_listener(listener: Any, change_type: str, key: str, old_value: Any, new_value: Any) -> None:
        try:
            if change_type == "added" and hasattr(listener, "on_config_added"):
                listener.on_config_added(key, new_value)
            elif change_type == "removed" and hasattr(listener, "on_config_removed"):
                listener.on_config_removed(key, old_value)
            else:
                listener.on_config_changed(key, old_value, new_value)
        except Exception as e:
            logger.error(f"配置变更通知失败 (key={key}, listener={listener.__class__.__name__}): {e}")

    def notify_reload(self) -> None:
        with self._lock:
            listeners_to_notify: list[ConfigChangeListener] = list(self._listeners)
            for key_listeners in self._key_listeners.values():
                listeners_to_notify.extend(key_listeners)
            for prefix_listeners in self._prefix_listeners.values():
                listeners_to_notify.extend(prefix_listeners)

        for listener in set(listeners_to_notify):
            try:
                if hasattr(listener, "on_config_reloaded"):
                    listener.on_config_reloaded()
            except Exception as e:
                logger.error(f"配置重载通知失败 (listener={listener.__class__.__name__}): {e}")

    def get_event_history(self, limit: int | None = None) -> list[ConfigChangeEvent]:
        with self._lock:
            events = self._event_history.copy()
            if limit:
                events = events[-limit:]
            return events

    def clear_history(self) -> None:
        with self._lock:
            self._event_history.clear()

    def get_listener_count(self) -> dict[str, int]:
        with self._lock:
            return {
                "global": len(self._listeners),
                "key_specific": sum(len(listeners) for listeners in self._key_listeners.values()),
                "prefix_specific": sum(len(listeners) for listeners in self._prefix_listeners.values()),
                "total_keys": len(self._key_listeners),
                "total_prefixes": len(self._prefix_listeners),
            }
