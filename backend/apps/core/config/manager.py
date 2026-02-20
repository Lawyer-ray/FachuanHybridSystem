"""
统一配置管理器

提供配置的加载、验证、访问和管理功能。
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, TypeVar, cast

import yaml

from ._cache import ConfigCache
from ._listeners import ConfigChangeEvent, ConfigChangeListener, ConfigNotificationManager
from ._watcher import HotReloadManager
from .exceptions import ConfigException, ConfigFileError, ConfigNotFoundError, ConfigTypeError, ConfigValidationError
from .providers.base import ConfigProvider
from .schema.schema import ConfigSchema
from .validators.base import CompositeValidator, ConfigValidator

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 重新导出，保持向后兼容
__all__ = [
    "ConfigManager",
    "ConfigCache",
    "ConfigChangeListener",
    "ConfigChangeEvent",
    "ConfigNotificationManager",
    "HotReloadManager",
]


class ConfigManager:
    """统一配置管理器"""

    def __init__(self, cache_max_size: int = 1000, cache_ttl: float = 3600.0) -> None:
        self._providers: list[ConfigProvider] = []
        self._cache = ConfigCache(cache_max_size, cache_ttl)
        self._raw_config: dict[str, Any] = {}
        self._schema: ConfigSchema = ConfigSchema()
        self._validator: ConfigValidator = CompositeValidator([])
        self._notification_manager = ConfigNotificationManager()
        self._lock = threading.RLock()
        self._loaded = False
        self._last_reload_time = 0.0
        self._hot_reload_manager = HotReloadManager(self)
        self._auto_reload_enabled = False
        self._steering_integration: Any = None

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

    def set_validator(self, validator: ConfigValidator) -> None:
        with self._lock:
            self._validator = validator

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
                        if provider.supports_reload() and hasattr(provider, "get_file_path"):
                            file_path = provider.get_file_path()
                            if file_path and os.path.exists(file_path):
                                self._hot_reload_manager.add_watch_file(file_path)
                    except Exception as e:
                        raise ConfigException(f"从 {provider.get_name()} 加载配置失败: {e}") from e
                self._validate_config()
                self._loaded = True
                self._last_reload_time = time.time()
                if self._auto_reload_enabled and not self._hot_reload_manager.is_enabled():
                    try:
                        self._hot_reload_manager.start()
                    except Exception as e:
                        logger.error(f"启动热重载失败: {e}")
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
        if self._validator:
            for key, value in self._raw_config.items():
                field_def = self._schema.get_field(key) if self._schema else None
                result = self._validator.validate(key, value, field_def, self._raw_config)
                if not result.is_valid:
                    raise ConfigValidationError(result.errors)

    def get(self, key: str, default: T | None = None) -> T:
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
                    result[key[len(prefix_with_dot):]] = value
                elif key == prefix:
                    result[key] = value
            return result

    def reload(self) -> bool:
        try:
            self.load(force_reload=True)
            return True
        except Exception:
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

    def get_cache_stats(self) -> dict[str, Any]:
        with self._lock:
            return self._cache.get_stats()

    def cleanup_cache(self) -> int:
        with self._lock:
            return self._cache.cleanup_expired()

    def enable_auto_reload(self) -> None:
        with self._lock:
            self._auto_reload_enabled = True
            if self._loaded:
                try:
                    self._hot_reload_manager.start()
                except Exception as e:
                    raise ConfigException(f"启用自动热重载失败: {e}") from e

    def disable_auto_reload(self) -> None:
        with self._lock:
            self._auto_reload_enabled = False
            self._hot_reload_manager.stop()

    def is_auto_reload_enabled(self) -> bool:
        return self._auto_reload_enabled

    def add_watch_file(self, file_path: str) -> None:
        self._hot_reload_manager.add_watch_file(file_path)

    def remove_watch_file(self, file_path: str) -> None:
        self._hot_reload_manager.remove_watch_file(file_path)

    def get_watched_files(self) -> list[str]:
        return self._hot_reload_manager.get_watched_files()

    def force_reload_from_file(self, file_path: str) -> bool:
        try:
            for provider in self._providers:
                if (
                    hasattr(provider, "get_file_path")
                    and provider.get_file_path() == file_path
                    and provider.supports_reload()
                ):
                    with self._lock:
                        old_config = self._raw_config.copy()
                        provider_config = provider.load()
                        if provider_config:
                            for key, value in provider_config.items():
                                self._raw_config[key] = value
                        self._validate_config()
                        self._cache.clear()
                        self._notify_changes(old_config, self._raw_config)
                        return True
            return False
        except Exception:
            return False

    def export(
        self,
        path: str,
        format: str = "yaml",
        mask_sensitive: bool = True,
        include_metadata: bool = True,
    ) -> None:
        if not self._loaded:
            self.load()
        try:
            with self._lock:
                export_data = self._prepare_export_data(mask_sensitive, include_metadata)
                os.makedirs(os.path.dirname(path), exist_ok=True)
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
                "export_time": datetime.now().isoformat(),
                "config_manager_version": "1.0.0",
                "total_configs": len(self._raw_config),
                "masked_sensitive": mask_sensitive,
            }
        config_data: dict[str, Any] = {}
        for key, value in self._raw_config.items():
            if self._is_sensitive_config(key) and mask_sensitive:
                config_data[key] = self._mask_sensitive_value(value)
            else:
                config_data[key] = value
        export_data["config"] = self._flatten_to_nested(config_data)
        return export_data

    def _is_sensitive_config(self, key: str) -> bool:
        if self._schema:
            field = self._schema.get_field(key)
            if field and field.sensitive:
                return True
        sensitive_keywords = [
            "password", "secret", "key", "token", "credential",
            "private", "auth", "api_key", "access_key",
        ]
        return any(kw in key.lower() for kw in sensitive_keywords)

    def _mask_sensitive_value(self, value: Any) -> str | None:
        if value is None:
            return None
        s = str(value)
        if len(s) <= 4:
            return "***"
        elif len(s) <= 8:
            return s[:2] + "***" + s[-1:]
        return s[:3] + "***" + s[-2:]

    def _flatten_to_nested(self, flat_config: dict[str, Any]) -> dict[str, Any]:
        nested: dict[str, Any] = {}
        for key, value in flat_config.items():
            keys = key.split(".")
            current = nested
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
        return nested

    def _export_yaml(self, path: str, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

    def _export_json(self, path: str, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)

    def import_config(
        self,
        path: str,
        format: str | None = None,
        validate: bool = True,
        merge: bool = True,
    ) -> None:
        if not os.path.exists(path):
            raise ConfigFileError(path, message="文件不存在")
        try:
            if format is None:
                format = self._detect_file_format(path)
            import_data = self._load_import_file(path, format)
            self._validate_import_data(import_data)
            config_data = self._extract_config_data(import_data)
            if validate:
                self._validate_imported_config(config_data)
            with self._lock:
                old_config = self._raw_config.copy()
                if merge:
                    self._merge_imported_config(config_data)
                else:
                    self._raw_config = config_data.copy()
                self._cache.clear()
                if validate:
                    self._validate_config()
                self._notify_changes(old_config, self._raw_config)
        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError, ConfigValidationError)):
                raise
            raise ConfigException(f"导入配置失败: {e}") from e

    def _detect_file_format(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".yaml", ".yml"):
            return "yaml"
        elif ext == ".json":
            return "json"
        raise ConfigException(f"无法检测文件格式: {path}")

    def _load_import_file(self, path: str, format: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                if format == "yaml":
                    return yaml.safe_load(f) or {}
                elif format == "json":
                    return json.load(f) or {}
                raise ConfigException(f"不支持的文件格式: {format}")
        except yaml.YAMLError as e:
            raise ConfigFileError(path, message=f"YAML格式错误: {e}") from e
        except json.JSONDecodeError as e:
            raise ConfigFileError(path, line=e.lineno, message=f"JSON格式错误: {e.msg}") from e
        except Exception as e:
            raise ConfigFileError(path, message=f"文件读取失败: {e}") from e

    def _validate_import_data(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ConfigValidationError(["导入数据必须是字典格式"])
        if "config" in data and not isinstance(data["config"], dict):
            raise ConfigValidationError(["配置数据必须是字典格式"])

    def _extract_config_data(self, import_data: dict[str, Any]) -> dict[str, Any]:
        config_data = import_data.get("config", import_data)
        return self._nested_to_flatten(config_data)

    def _nested_to_flatten(self, nested_config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for key, value in nested_config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(self._nested_to_flatten(value, full_key))
            else:
                flat[full_key] = value
        return flat

    def _validate_imported_config(self, config_data: dict[str, Any]) -> None:
        errors: list[str] = []
        if self._schema:
            for key, value in config_data.items():
                field = self._schema.get_field(key)
                if field and not field.is_valid_value(value):
                    errors.append(f"配置项 '{key}' 值无效: {value}")
        if self._validator:
            for key, value in config_data.items():
                field_def = self._schema.get_field(key) if self._schema else None
                result = self._validator.validate(key, value, field_def, config_data)
                if not result.is_valid:
                    errors.extend(result.errors)
        if errors:
            raise ConfigValidationError(errors)

    def _merge_imported_config(self, config_data: dict[str, Any]) -> None:
        for key, value in config_data.items():
            self._raw_config[key] = value

    def create_snapshot(self, name: str | None = None, description: str = "") -> str:
        if not self._loaded:
            self.load()
        try:
            timestamp = datetime.now()
            snapshot_id = timestamp.strftime("%Y%m%d_%H%M%S")
            snapshot_name = f"{snapshot_id}_{name}" if name else snapshot_id
            snapshot_data = {
                "id": snapshot_id,
                "name": snapshot_name,
                "description": description,
                "created_at": timestamp.isoformat(),
                "config_count": len(self._raw_config),
                "config": self._raw_config.copy(),
            }
            snapshot_dir = self._get_snapshot_directory()
            os.makedirs(snapshot_dir, exist_ok=True)
            snapshot_path = os.path.join(snapshot_dir, f"{snapshot_name}.yaml")
            with open(snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(snapshot_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
            return snapshot_id
        except Exception as e:
            raise ConfigException(f"创建配置快照失败: {e}") from e

    def restore_snapshot(self, snapshot_id: str, validate: bool = True) -> None:
        try:
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if not snapshot_path:
                raise ConfigFileError(snapshot_id, message="快照不存在")
            with open(snapshot_path, encoding="utf-8") as f:
                snapshot_data = yaml.safe_load(f)
            self._validate_snapshot_data(snapshot_data)
            config_data = snapshot_data["config"]
            if validate:
                self._validate_imported_config(config_data)
            with self._lock:
                old_config = self._raw_config.copy()
                self._raw_config = config_data.copy()
                self._cache.clear()
                if validate:
                    self._validate_config()
                self._notify_changes(old_config, self._raw_config)
        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError, ConfigValidationError)):
                raise
            raise ConfigException(f"恢复配置快照失败: {e}") from e

    def list_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        snapshot_dir = self._get_snapshot_directory()
        if not os.path.exists(snapshot_dir):
            return snapshots
        try:
            for filename in os.listdir(snapshot_dir):
                if not filename.endswith(".yaml"):
                    continue
                snapshot_path = os.path.join(snapshot_dir, filename)
                try:
                    with open(snapshot_path, encoding="utf-8") as f:
                        sd = yaml.safe_load(f)
                    snapshots.append({
                        "id": sd.get("id", ""),
                        "name": sd.get("name", ""),
                        "description": sd.get("description", ""),
                        "created_at": sd.get("created_at", ""),
                        "config_count": sd.get("config_count", 0),
                        "file_path": snapshot_path,
                    })
                except Exception:
                    continue
            snapshots.sort(key=lambda x: x["created_at"], reverse=True)
        except Exception as e:
            raise ConfigException(f"列出快照失败: {e}") from e
        return snapshots

    def delete_snapshot(self, snapshot_id: str) -> bool:
        try:
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if snapshot_path and os.path.exists(snapshot_path):
                os.remove(snapshot_path)
                return True
            return False
        except Exception:
            return False

    def _get_snapshot_directory(self) -> str:
        return os.path.join(os.getcwd(), ".config_snapshots")

    def _find_snapshot_file(self, snapshot_id: str) -> str | None:
        snapshot_dir = self._get_snapshot_directory()
        if not os.path.exists(snapshot_dir):
            return None
        direct_path = os.path.join(snapshot_dir, f"{snapshot_id}.yaml")
        if os.path.exists(direct_path):
            return direct_path
        for filename in os.listdir(snapshot_dir):
            if filename.endswith(".yaml") and snapshot_id in filename:
                return os.path.join(snapshot_dir, filename)
        return None

    def _validate_snapshot_data(self, snapshot_data: dict[str, Any]) -> None:
        required_fields = ["id", "name", "created_at", "config"]
        errors = [f"快照数据缺少必需字段: {f}" for f in required_fields if f not in snapshot_data]
        if "config" in snapshot_data and not isinstance(snapshot_data["config"], dict):
            errors.append("快照配置数据必须是字典格式")
        if errors:
            raise ConfigValidationError(errors)

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

    def enable_steering_integration(self) -> None:
        if self._steering_integration is None:
            try:
                from .steering_integration import SteeringIntegrationManager
                self._steering_integration = SteeringIntegrationManager(self)
                logger.info("Steering 系统集成已启用")
            except ImportError as e:
                logger.warning(f"无法启用 Steering 集成: {e}")

    def get_steering_integration(self) -> Any:
        if self._steering_integration is None:
            self.enable_steering_integration()
        return self._steering_integration

    def load_steering_specifications(self, target_file_path: str) -> list[Any]:
        integration = self.get_steering_integration()
        if integration:
            return cast(list[Any], integration.load_specifications_for_file(target_file_path))
        return []
