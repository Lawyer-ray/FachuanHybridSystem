"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from apps.core.config.exceptions import ConfigNotFoundError, ConfigTypeError

if TYPE_CHECKING:
    from apps.core.config.manager import ConfigManager

T = TypeVar("T")


class ConfigQueryService:
    def __init__(self, manager: ConfigManager) -> None:
        self._m = manager

    def get(self, key: str, default: T | None = None) -> T:
        if not self._m._loaded:
            with self._m._lock:
                has_existing = key in self._m._raw_config or self._get_nested_value(key) is not None
            if not has_existing:
                self._m.load()

        with self._m._lock:
            cached_value = self._m._cache.get(key)
            if cached_value is not None:
                return cast(T, cached_value)

            if key in self._m._raw_config:
                value = self._m._raw_config[key]
                self._m._cache.set(key, value)
                return cast(T, value)

            value = self._get_nested_value(key)
            if value is not None:
                self._m._cache.set(key, value)
                return cast(T, value)

            if self._m._schema:
                field = self._m._schema.get_field(key)
                if field and field.default is not None:
                    return cast(T, field.default)

            if default is not None:
                return default

            suggestions = self._m._schema.get_suggestions(key) if self._m._schema else []
            raise ConfigNotFoundError(key, suggestions)

    def get_typed(self, key: str, type_: type[T], default: T | None = None) -> T:
        value = self.get(key, default)
        if value is None:
            return cast(T, value)
        if isinstance(value, type_):
            return value
        try:
            return cast(T, self._convert_type(value, type_))
        except (ValueError, TypeError) as e:
            raise ConfigTypeError(key, type_, type(value)) from e

    def has(self, key: str) -> bool:
        if not self._m._loaded:
            self._m.load()
        with self._m._lock:
            return key in self._m._raw_config or self._get_nested_value(key) is not None

    def get_all(self) -> dict[str, Any]:
        if not self._m._loaded:
            self._m.load()
        with self._m._lock:
            return self._m._raw_config.copy()

    def get_by_prefix(self, prefix: str) -> dict[str, Any]:
        if not self._m._loaded:
            self._m.load()
        with self._m._lock:
            result: dict[str, Any] = {}
            prefix_with_dot = f"{prefix}."
            for key, value in self._m._raw_config.items():
                if key.startswith(prefix_with_dot):
                    relative_key = key[len(prefix_with_dot) :]
                    result[relative_key] = value
                elif key == prefix:
                    result[key] = value
            return result

    def get_cache_stats(self) -> dict[str, Any]:
        with self._m._lock:
            return self._m._cache.get_stats()

    def cleanup_cache(self) -> int:
        with self._m._lock:
            return self._m._cache.cleanup_expired()

    def _get_nested_value(self, key: str) -> Any:
        keys = key.split(".")
        for i in range(len(keys)):
            partial_key = ".".join(keys[: i + 1])
            if partial_key in self._m._raw_config and i == len(keys) - 1:
                return self._m._raw_config[partial_key]
        return None

    def _convert_type(self, value: Any, target_type: type) -> Any:
        if target_type is bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is str:
            return str(value)
        if target_type is list:
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return list(value)
        return target_type(value)
