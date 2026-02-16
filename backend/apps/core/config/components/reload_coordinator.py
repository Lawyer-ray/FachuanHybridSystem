"""Module for reload coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.config.exceptions import ConfigException

if TYPE_CHECKING:
    from apps.core.config.manager import ConfigManager


class ConfigReloadCoordinator:
    def __init__(self, manager: ConfigManager) -> None:
        self._m = manager

    def enable_auto_reload(self) -> None:
        with self._m._lock:
            self._m._auto_reload_enabled = True
            if self._m._loaded:
                try:
                    self._m._hot_reload_manager.start()
                except Exception as e:
                    raise ConfigException(f"启用自动热重载失败: {e}") from e

    def disable_auto_reload(self) -> None:
        with self._m._lock:
            self._m._auto_reload_enabled = False
            self._m._hot_reload_manager.stop()

    def is_auto_reload_enabled(self) -> bool:
        return self._m._auto_reload_enabled

    def add_watch_file(self, file_path: str) -> None:
        self._m._hot_reload_manager.add_watch_file(file_path)

    def remove_watch_file(self, file_path: str) -> None:
        self._m._hot_reload_manager.remove_watch_file(file_path)

    def get_watched_files(self) -> list[str]:
        return self._m._hot_reload_manager.get_watched_files()
