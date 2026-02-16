"""Module for manager tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import yaml

from apps.core.path import Path

from .clock import utc_now
from .exceptions import ConfigException, ConfigFileError, ConfigValidationError

if TYPE_CHECKING:
    from .manager import ConfigManager

logger = logging.getLogger("apps.core.config.manager")


def create_snapshot(self: ConfigManager, name: str | None = None, description: str = "") -> str:
    if not self._loaded:
        self.load()

    try:
        timestamp = utc_now()
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

        snapshot_dir = _get_snapshot_directory(self)
        Path(str(snapshot_dir)).makedirs_p()

        snapshot_path = str(Path(str(snapshot_dir)) / f"{snapshot_name}.yaml")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            yaml.dump(snapshot_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

        return snapshot_id
    except Exception as e:
        raise ConfigException(f"创建配置快照失败: {e}") from e


def restore_snapshot(self: ConfigManager, snapshot_id: str, validate: bool = True) -> None:
    try:
        snapshot_path = _find_snapshot_file(self, snapshot_id)
        if not snapshot_path:
            raise ConfigFileError(snapshot_id, message="快照不存在")

        with open(snapshot_path, encoding="utf-8") as f:
            snapshot_data = yaml.safe_load(f)

        _validate_snapshot_data(self, snapshot_data)
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


def list_snapshots(self: Any) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    snapshot_dir = _get_snapshot_directory(self)

    if not Path(str(snapshot_dir)).exists():
        return snapshots

    try:
        for snapshot_file in Path(str(snapshot_dir)).files("*.yaml"):
            snapshot_path = str(snapshot_file)
            try:
                with open(snapshot_path, encoding="utf-8") as f:
                    snapshot_data = yaml.safe_load(f)

                snapshots.append(
                    {
                        "id": snapshot_data.get("id", ""),
                        "name": snapshot_data.get("name", ""),
                        "description": snapshot_data.get("description", ""),
                        "created_at": snapshot_data.get("created_at", ""),
                        "config_count": snapshot_data.get("config_count", 0),
                        "file_path": snapshot_path,
                    }
                )
            except Exception:
                logger.exception("操作失败")

                continue

        snapshots.sort(key=lambda x: x["created_at"], reverse=True)
    except Exception as e:
        raise ConfigException(f"列出快照失败: {e}") from e

    return snapshots


def delete_snapshot(self: Any, snapshot_id: str) -> bool:
    try:
        snapshot_path = _find_snapshot_file(self, snapshot_id)
        if snapshot_path and Path(str(snapshot_path)).exists():
            Path(str(snapshot_path)).remove_p()
            return True
        return False
    except Exception:
        # 静默处理:文件操作失败不影响主流程
        # 静默处理:文件操作失败不影响主流程
        # 静默处理:文件操作失败不影响主流程

        # 静默处理:文件操作失败不影响主流程

        return False


def _get_snapshot_directory(self: Any) -> str:
    return str(Path.cwd() / ".config_snapshots")


def _find_snapshot_file(self: Any, snapshot_id: str) -> str | None:
    snapshot_dir = _get_snapshot_directory(self)
    if not Path(str(snapshot_dir)).exists():
        return None

    direct_path = Path(str(snapshot_dir)) / f"{snapshot_id}.yaml"
    if direct_path.exists():
        return str(direct_path)

    for snapshot_file in Path(str(snapshot_dir)).files("*.yaml"):
        if snapshot_id in snapshot_file.name:
            return str(snapshot_file)

    return None


def _validate_snapshot_data(self: ConfigManager, snapshot_data: dict[str, Any]) -> None:
    required_fields = ["id", "name", "created_at", "config"]
    errors: list[str] = []

    for field_name in required_fields:
        if field_name not in snapshot_data:
            errors.append(f"快照数据缺少必需字段: {field_name}")

    if "config" in snapshot_data and not isinstance(snapshot_data["config"], dict):
        errors.append("快照配置数据必须是字典格式")

    if errors:
        raise ConfigValidationError(errors)


def __getitem__(self: Any, key: str) -> Any:
    return self.get(key)


def __setitem__(self: Any, key: str, value: Any) -> None:
    self.set(key, value)


def __contains__(self: Any, key: str) -> bool:
    return cast(bool, self.has(key))


def __len__(self: Any) -> int:
    if not self._loaded:
        self.load()
    return len(self._raw_config)


def enable_steering_integration(self: Any) -> None:
    if self._steering_integration is None:
        try:
            from .steering.integration import SteeringIntegrationManager

            self._steering_integration = SteeringIntegrationManager(self)
            logger.info("Steering 系统集成已启用")
        except ImportError as e:
            logger.warning(f"无法启用 Steering 集成: {e}")


def get_steering_integration(self: Any) -> Any:
    if self._steering_integration is None:
        enable_steering_integration(self)
    return self._steering_integration


def load_steering_specifications(self: Any, target_file_path: str) -> list[Any]:
    integration = get_steering_integration(self)
    if integration:
        return cast(list[Any], integration.load_specifications_for_file(target_file_path))
    return []
