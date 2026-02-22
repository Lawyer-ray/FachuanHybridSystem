"""Business logic services."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

import yaml

from apps.core.config.clock import utc_now
from apps.core.config.exceptions import ConfigException, ConfigValidationError
from apps.core.config.notifications import ConfigChangeListener
from apps.core.config.schema.schema import ConfigSchema
from apps.core.config.validators.base import ConfigValidator
from apps.core.path import Path

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ConfigCommandService:
    def __init__(self, manager: Any) -> None:
        self._m = manager

    def set_schema(self, schema: ConfigSchema) -> None:
        with self._m._lock:
            self._m._schema = schema

    def set_validator(self, validator: ConfigValidator) -> None:
        with self._m._lock:
            self._m._validator = validator

    def load(self, force_reload: bool = False) -> None:
        with self._m._lock:
            if self._m._loaded and not force_reload:
                return

            old_raw_config = self._m._raw_config.copy()
            self._m._raw_config.clear()
            self._m._cache.clear()

            try:
                for provider in self._m._provider_registry.iter():
                    try:
                        provider_config = provider.load()
                        if provider_config:
                            self._merge_config(provider_config)

                        if provider.supports_reload() and hasattr(provider, "get_file_path"):
                            file_path = provider.get_file_path()
                            if file_path and Path(str(file_path)).exists():
                                self._m._hot_reload_manager.add_watch_file(file_path)

                    except Exception as e:
                        raise ConfigException(f"从 {provider.get_name()} 加载配置失败: {e}") from e

                self._validate_config()

                self._m._loaded = True
                self._m._last_reload_time = time.time()

                if self._m._auto_reload_enabled and not self._m._hot_reload_manager.is_enabled():
                    try:
                        self._m._hot_reload_manager.start()
                    except Exception as e:
                        logger.error(f"启动热重载失败: {e}")

                self._m._notify_changes(old_raw_config, self._m._raw_config)
                self._m._notification_manager.notify_reload()

            except Exception as e:
                self._m._raw_config = old_raw_config
                self._m._cache.clear()
                raise e

    def reload(self) -> bool:
        try:
            self.load(force_reload=True)
            return True
        except (OSError, ValueError, KeyError):
            return False

    def set(self, key: str, value: Any) -> None:
        with self._m._lock:
            old_value = self._m._raw_config.get(key)
            self._m._raw_config[key] = value
            self._m._cache.set(key, value)
            self._m._notification_manager.notify_change(key, old_value, value)

    def clear_cache(self) -> None:
        with self._m._lock:
            self._m._cache.clear()
            self._m._loaded = False

    def add_listener(
        self, listener: ConfigChangeListener, key_filter: str | None = None, prefix_filter: str | None = None
    ) -> None:
        self._m._notification_manager.add_listener(listener, key_filter, prefix_filter)

    def remove_listener(self, listener: ConfigChangeListener) -> None:
        self._m._notification_manager.remove_listener(listener)

    def force_reload_from_file(self, file_path: str) -> bool:
        provider = self._m._provider_registry.find_reloadable_provider_by_file_path(file_path)
        if not provider:
            return False

        try:
            with self._m._lock:
                old_config = self._m._raw_config.copy()
                provider_config = provider.load()
                if provider_config:
                    for key, value in provider_config.items():
                        self._m._raw_config[key] = value

                self._validate_config()
                self._m._cache.clear()
                self._m._notify_changes(old_config, self._m._raw_config)
                return True
        except (OSError, ValueError, KeyError):
            return False

    def export(
        self, path: str, format: str = "yaml", mask_sensitive: bool = True, include_metadata: bool = True
    ) -> None:
        if not self._m._loaded:
            self._m.load()

        try:
            with self._m._lock:
                export_data = self._prepare_export_data(mask_sensitive, include_metadata)
                Path(str(path)).parent.makedirs_p()
                if format.lower() == "yaml":
                    self._export_yaml(path, export_data)
                elif format.lower() == "json":
                    self._export_json(path, export_data)
                else:
                    raise ConfigException(f"不支持的导出格式: {format}")
        except Exception as e:
            raise ConfigException(f"导出配置失败: {e}") from e

    def _prepare_export_data(self, mask_sensitive: bool, include_metadata: bool) -> dict[str, Any]:
        export_data: dict[str, Any] = {}

        if include_metadata:
            export_data["_metadata"] = {
                "export_time": utc_now().isoformat(),
                "config_manager_version": "1.0.0",
                "total_configs": len(self._m._raw_config),
                "masked_sensitive": mask_sensitive,
            }

        config_data: dict[str, Any] = {}
        for key, value in self._m._raw_config.items():
            is_sensitive = self._is_sensitive_config(key)
            if is_sensitive and mask_sensitive:
                config_data[key] = self._mask_sensitive_value(value)
            else:
                config_data[key] = value

        export_data["config"] = self._flatten_to_nested(config_data)
        return export_data

    def _is_sensitive_config(self, key: str) -> bool:
        if self._m._schema:
            field = self._m._schema.get_field(key)
            if field and getattr(field, "sensitive", False):
                return True

        key_lower = (key or "").lower()
        sensitive_keywords = ["password", "secret", "token", "key", "api_key", "credential", "private"]
        return any(keyword in key_lower for keyword in sensitive_keywords)

    def _mask_sensitive_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if len(value) <= 4:
                return "*" * len(value)
            return value[:2] + "*" * (len(value) - 4) + value[-2:]
        if isinstance(value, (int, float)):
            return "***"
        if isinstance(value, list):
            return [self._mask_sensitive_value(item) for item in value]
        if isinstance(value, dict):
            return {k: self._mask_sensitive_value(v) for k, v in value.items()}
        return "***"

    def _flatten_to_nested(self, flat_data: dict[str, Any]) -> dict[str, Any]:
        nested: dict[str, Any] = {}
        for key, value in flat_data.items():
            parts = str(key).split(".")
            current = nested
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return nested

    def _export_yaml(self, path: str, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _export_json(self, path: str, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _merge_config(self, config: dict[str, Any], prefix: str = "") -> None:
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._merge_config(value, full_key)
                continue
            if full_key not in self._m._raw_config:
                self._m._raw_config[full_key] = value

    def _validate_config(self) -> None:
        if self._m._schema:
            self._m._schema.validate_and_raise(self._m._raw_config)

        if self._m._validator:
            for key, value in self._m._raw_config.items():
                field_def = self._m._schema.get_field(key) if self._m._schema else None
                result = self._m._validator.validate(key, value, field_def, self._m._raw_config)
                if not result.is_valid:
                    raise ConfigValidationError(result.errors)
