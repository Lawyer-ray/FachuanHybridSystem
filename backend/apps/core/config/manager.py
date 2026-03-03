"""统一配置管理器"""

import logging
import threading
import time
from typing import Any, TypeVar, cast

from .cache import ConfigCache
from .exceptions import ConfigException, ConfigNotFoundError, ConfigTypeError
from .notifications import ConfigChangeEvent, ConfigChangeListener, ConfigNotificationManager
from .providers.base import ConfigProvider
from .schema.schema import ConfigSchema

logger = logging.getLogger(__name__)

T = TypeVar("T")

__all__ = [
    "ConfigManager",
    "ConfigChangeListener",
    "ConfigChangeEvent",
]


class ConfigManager:
    """统一配置管理器"""

    def __init__(self, cache_max_size: int = 1000, cache_ttl: float = 3600.0) -> None:
        self._providers: list[ConfigProvider] = []
        self._cache = ConfigCache(cache_max_size, cache_ttl)
        self._raw_config: dict[str, Any] = {}
        self._schema: ConfigSchema = ConfigSchema()
        self._notification_manager = ConfigNotificationManager()
        self._lock = threading.RLock()
        self._loaded = False
        self._last_reload_time = 0.0

    def add_provider(self, provider: ConfigProvider) -> None:
        with self._lock:
            self._providers.append(provider)
            self._providers.sort(key=lambda p: p.priority, reverse=True)

    def remove_provider(self, provider_class: type) -> None:
        with self._lock:
            self._providers = [p for p in self._providers if not isinstance(p, provider_class)]

    def set_schema(self, schema: ConfigSchema) -> None:
        with self._lock:
            self._schema = schema

    def load(self, force_reload: bool = False) -> None:
        with self._lock:
            if self._loaded and not force_reload:
                return
            old_raw_config = self._raw_config.copy()
            self._raw_config.clear()
            self._cache.clear()
            try:
                for provider in self._providers:
                    try:
                        provider_config = provider.load()
                        if provider_config:
                            self._merge_config(provider_config)
                    except Exception as e:
                        raise ConfigException(f"从 {provider.get_name()} 加载配置失败: {e}") from e
                self._validate_config()
                self._loaded = True
                self._last_reload_time = time.time()
                self._notify_changes(old_raw_config, self._raw_config)
                self._notification_manager.notify_reload()
            except Exception as e:
                self._raw_config = old_raw_config
                self._cache.clear()
                raise e

    def _merge_config(self, config: dict[str, Any], prefix: str = "") -> None:
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._merge_config(value, full_key)
            elif full_key not in self._raw_config:
                self._raw_config[full_key] = value

    def _validate_config(self) -> None:
        if self._schema:
            self._schema.validate_and_raise(self._raw_config)

    def get(self, key: str, default: T | None = None) -> T:
        with self._lock:
            if key in self._raw_config:
                cached_value = self._cache.get(key)
                if cached_value is not None:
                    return cast(T, cached_value)
                value = self._raw_config[key]
                self._cache.set(key, value)
                return cast(T, value)
        if not self._loaded:
            self.load()
        with self._lock:
            cached_value = self._cache.get(key)
            if cached_value is not None:
                return cast(T, cached_value)
            if key in self._raw_config:
                value = self._raw_config[key]
                self._cache.set(key, value)
                return cast(T, value)
            value = self._get_nested_value(key)
            if value is not None:
                self._cache.set(key, value)
                return cast(T, value)
            if self._schema:
                field = self._schema.get_field(key)
                if field and field.default is not None:
                    return cast(T, field.default)
            if default is not None:
                return default
            suggestions = self._schema.get_suggestions(key) if self._schema else []
            raise ConfigNotFoundError(key, suggestions)

    def _get_nested_value(self, key: str) -> Any:
        keys = key.split(".")
        for i in range(len(keys)):
            partial_key = ".".join(keys[: i + 1])
            if partial_key in self._raw_config:
                if i == len(keys) - 1:
                    return self._raw_config[partial_key]
        return None

    def get_typed(self, key: str, type_: type[T], default: T | None = None) -> T | None:
        value = self.get(key, default)
        if value is None:
            return None
        if isinstance(value, type_):
            return value
        try:
            return cast(T, self._convert_type(value, type_))
        except (ValueError, TypeError) as e:
            raise ConfigTypeError(key, type_, type(value)) from e

    def _convert_type(self, value: Any, target_type: type) -> Any:
        if target_type is bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        elif target_type is int:
            return int(value)
        elif target_type is float:
            return float(value)
        elif target_type is str:
            return str(value)
        elif target_type is list:
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return list(value)
        return target_type(value)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            old_value = self._raw_config.get(key)
            self._raw_config[key] = value
            self._cache.set(key, value)
            self._notification_manager.notify_change(key, old_value, value)

    def has(self, key: str) -> bool:
        if not self._loaded:
            self.load()
        with self._lock:
            return key in self._raw_config or self._get_nested_value(key) is not None

    def get_all(self) -> dict[str, Any]:
        if not self._loaded:
            self.load()
        with self._lock:
            return self._raw_config.copy()

    def get_by_prefix(self, prefix: str) -> dict[str, Any]:
        if not self._loaded:
            self.load()
        with self._lock:
            result: dict[str, Any] = {}
            prefix_with_dot = f"{prefix}."
            for key, value in self._raw_config.items():
                if key.startswith(prefix_with_dot):
                    result[key[len(prefix_with_dot) :]] = value
                elif key == prefix:
                    result[key] = value
            return result

    def reload(self) -> bool:
        try:
            self.load(force_reload=True)
            return True
        except (OSError, ValueError, KeyError):
            return False

    def add_listener(
        self,
        listener: ConfigChangeListener,
        key_filter: str | None = None,
        prefix_filter: str | None = None,
    ) -> None:
        self._notification_manager.add_listener(listener, key_filter, prefix_filter)

    def remove_listener(self, listener: ConfigChangeListener) -> None:
        self._notification_manager.remove_listener(listener)

    def _notify_changes(self, old_config: dict[str, Any], new_config: dict[str, Any]) -> None:
        all_keys = set(old_config.keys()) | set(new_config.keys())
        for key in all_keys:
            old_value = old_config.get(key)
            new_value = new_config.get(key)
            if old_value != new_value:
                self._notification_manager.notify_change(key, old_value, new_value)

    def is_loaded(self) -> bool:
        return self._loaded

    def get_last_reload_time(self) -> float:
        return self._last_reload_time

    def get_provider_count(self) -> int:
        return len(self._providers)

    def get_listener_count(self) -> dict[str, int]:
        return self._notification_manager.get_listener_count()

    def get_change_history(self, limit: int | None = None) -> list[ConfigChangeEvent]:
        return self._notification_manager.get_event_history(limit)

    def clear_change_history(self) -> None:
        self._notification_manager.clear_history()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._loaded = False

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        if not self._loaded:
            self.load()
        return len(self._raw_config)
