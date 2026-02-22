"""配置文件热重载监控模块"""

import logging
import os
import threading
import time
import weakref
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEventHandler

from .exceptions import ConfigException

if TYPE_CHECKING:
    from .manager import ConfigManager

logger = logging.getLogger(__name__)


class ConfigFileWatcher(FileSystemEventHandler):
    """配置文件监控器"""

    def __init__(self, config_manager: "ConfigManager", watched_files: list[str]) -> None:
        self.config_manager: Any = weakref.ref(config_manager)
        self.watched_files = {os.path.abspath(f) for f in watched_files}
        self.last_reload_time = 0.0
        self.reload_debounce = 1.0

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        file_path = os.path.abspath(event.src_path)
        if file_path not in self.watched_files:
            return
        current_time = time.time()
        if current_time - self.last_reload_time < self.reload_debounce:
            return
        self.last_reload_time = current_time
        manager = self.config_manager()
        if manager:
            try:
                manager.reload()
            except Exception as e:
                logger.error(f"配置热重载失败: {e}")


class HotReloadManager:
    """热重载管理器"""

    def __init__(self, config_manager: "ConfigManager") -> None:
        self.config_manager = config_manager
        self.observer: Any = None
        self.watched_files: list[str] = []
        self.enabled = False
        self._lock = threading.Lock()

    def add_watch_file(self, file_path: str) -> None:
        with self._lock:
            abs_path = os.path.abspath(file_path)
            if abs_path not in self.watched_files:
                self.watched_files.append(abs_path)
                if self.enabled and self.observer:
                    self._restart_observer()

    def remove_watch_file(self, file_path: str) -> None:
        with self._lock:
            abs_path = os.path.abspath(file_path)
            if abs_path in self.watched_files:
                self.watched_files.remove(abs_path)
                if self.enabled and self.observer:
                    self._restart_observer()

    def start(self) -> None:
        with self._lock:
            if self.enabled or not self.watched_files:
                return
            try:
                from watchdog.observers import Observer

                self.observer = Observer()
                event_handler = ConfigFileWatcher(self.config_manager, self.watched_files)
                watched_dirs: set[str] = set()
                for file_path in self.watched_files:
                    dir_path = os.path.dirname(file_path)
                    if dir_path not in watched_dirs:
                        self.observer.schedule(event_handler, dir_path, recursive=False)
                        watched_dirs.add(dir_path)
                self.observer.start()
                self.enabled = True
            except Exception as e:
                if self.observer:
                    self.observer.stop()
                    self.observer = None
                raise ConfigException(f"启动热重载监控失败: {e}") from e

    def stop(self) -> None:
        with self._lock:
            if not self.enabled or not self.observer:
                return
            try:
                self.observer.stop()
                self.observer.join(timeout=5.0)
                self.observer = None
                self.enabled = False
            except Exception as e:
                logger.error(f"停止热重载监控时出错: {e}")

    def _restart_observer(self) -> None:
        if self.enabled:
            self.stop()
            self.start()

    def is_enabled(self) -> bool:
        return self.enabled

    def get_watched_files(self) -> list[str]:
        with self._lock:
            return self.watched_files.copy()
