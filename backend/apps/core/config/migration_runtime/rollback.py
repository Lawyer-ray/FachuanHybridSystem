"""Module for rollback."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from apps.core.config.exceptions import ConfigException
from apps.core.config.migration_tracker import MigrationEventType, MigrationStateTracker
from apps.core.config.migration_types import MigrationLog, MigrationStatus
from apps.core.path import Path

logger = logging.getLogger(__name__)


@dataclass
class RollbackState:
    rollback_points: dict[str, dict[str, Any]]
    rollback_stack: list[tuple[str, str, Any, Any]]


class RollbackManager:
    def __init__(
        self,
        *,
        backup_dir: str,
        config_manager: Any,
        compatibility_layer: Any,
        tracker: MigrationStateTracker,
        migration_logs: list[MigrationLog],
        utc_now: Any,
    ) -> None:
        self.backup_dir = backup_dir
        self.config_manager = config_manager
        self.compatibility_layer = compatibility_layer
        self.tracker = tracker
        self.migration_logs = migration_logs
        self.utc_now = utc_now
        self.state = RollbackState(rollback_points={}, rollback_stack=[])

    def track_config_change(self, migration_id: str, key: str, old_value: Any, new_value: Any) -> None:
        self.state.rollback_stack.append((migration_id, key, old_value, new_value))
        self.tracker.record_config_migration(migration_id, key, old_value, new_value)

    def create_rollback_point(self, migration_id: str, point_name: str) -> None:
        rollback_point = {
            "migration_id": migration_id,
            "point_name": point_name,
            "timestamp": self.utc_now().isoformat(),
            "config_state": self.config_manager.get_all() if self.config_manager.is_loaded() else {},
            "django_state": self.compatibility_layer.get_all_django_configs(),
            "rollback_stack": self.state.rollback_stack.copy(),
        }

        point_key = f"{migration_id}_{point_name}"
        self.state.rollback_points[point_key] = rollback_point

        rollback_file = str(Path(self.backup_dir) / f"{point_key}_rollback_point.json")
        with open(rollback_file, "w", encoding="utf-8") as f:
            json.dump(rollback_point, f, ensure_ascii=False, indent=2, default=str)

        self.tracker.record_config_migration(
            migration_id, f"rollback_point_{point_name}", None, point_name, "rollback_point"
        )

    def rollback_to_point(self, migration_id: str, point_name: str) -> bool:
        try:
            point_key = f"{migration_id}_{point_name}"
            rollback_point = self.state.rollback_points.get(point_key)

            if not rollback_point:
                rollback_file = str(Path(self.backup_dir) / f"{point_key}_rollback_point.json")
                if Path(rollback_file).exists():
                    with open(rollback_file, encoding="utf-8") as f:
                        rollback_point = json.load(f)
                else:
                    raise ConfigException(f"找不到回滚点: {point_name}")

            self.tracker.record_error(migration_id, f"开始回滚到回滚点: {point_name}", "ROLLBACK_STARTED")

            if rollback_point is None:
                raise ValueError("Rollback point cannot be None")
            config_state = rollback_point.get("config_state", {})
            if config_state:
                self.config_manager.clear_cache()
                for key, value in config_state.items():
                    self.config_manager.set(key, value)

            self.state.rollback_stack = rollback_point.get("rollback_stack", [])

            self.tracker.record_config_migration(
                migration_id, f"rollback_completed_{point_name}", None, point_name, "rollback"
            )

            return True

        except Exception as e:
            logger.exception("操作失败")
            self.tracker.record_error(migration_id, f"回滚失败: {e!s}", "ROLLBACK_FAILED")
            return False

    def auto_rollback_on_error(self, migration_id: str, error: Exception) -> bool:
        try:
            self.tracker.record_error(migration_id, f"触发自动回滚: {error!s}", "AUTO_ROLLBACK_TRIGGERED")

            success = self._execute_rollback_operations(migration_id)

            if success:
                for migration_log in self.migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = self.utc_now()
                        migration_log.error_message = f"自动回滚: {error!s}"
                        break

                self.tracker.record_config_migration(
                    migration_id, "auto_rollback_success", None, "success", "auto_rollback"
                )
            else:
                self.tracker.record_error(migration_id, "自动回滚失败", "AUTO_ROLLBACK_FAILED")

            return success

        except Exception as rollback_error:
            logger.exception("操作失败")
            self.tracker.record_error(
                migration_id, f"自动回滚过程中发生错误: {rollback_error!s}", "AUTO_ROLLBACK_ERROR"
            )
            return False

    def _execute_rollback_operations(self, migration_id: str) -> bool:
        try:
            rollback_operations = []
            for operation in reversed(self.state.rollback_stack):
                op_migration_id, key, old_value, new_value = operation
                if op_migration_id == migration_id:
                    rollback_operations.append((key, old_value, new_value))

            for key, old_value, new_value in rollback_operations:
                try:
                    if old_value is None:
                        if self.config_manager.has(key):
                            pass
                    else:
                        self.config_manager.set(key, old_value)
                    self.tracker.record_config_migration(migration_id, key, new_value, old_value, "rollback")
                except Exception as e:
                    logger.exception("操作失败")
                    self.tracker.record_error(
                        migration_id, f"回滚配置项 {key} 失败: {e!s}", "ROLLBACK_CONFIG_FAILED", config_key=key
                    )
                    continue

            self.state.rollback_stack = [op for op in self.state.rollback_stack if op[0] != migration_id]
            return True

        except Exception as e:
            logger.exception("操作失败")
            self.tracker.record_error(migration_id, f"执行回滚操作失败: {e!s}", "EXECUTE_ROLLBACK_FAILED")
            return False

    def enhanced_rollback_migration(self, migration_id: str, rollback_strategy: str = "full") -> bool:
        try:
            self.tracker.record_error(
                migration_id, f"开始增强回滚 (策略: {rollback_strategy})", "ENHANCED_ROLLBACK_STARTED"
            )

            if rollback_strategy == "full":
                success = self.rollback_migration(migration_id)
            elif rollback_strategy == "partial":
                success = self._partial_rollback(migration_id)
            elif rollback_strategy == "config_only":
                success = self._config_only_rollback(migration_id)
            else:
                raise ConfigException(f"不支持的回滚策略: {rollback_strategy}")

            if success:
                for migration_log in self.migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = self.utc_now()
                        break

                self.tracker.record_config_migration(
                    migration_id,
                    f"enhanced_rollback_success_{rollback_strategy}",
                    None,
                    "success",
                    "enhanced_rollback",
                )

            return success

        except Exception as e:
            logger.exception("操作失败")
            self.tracker.record_error(migration_id, f"增强回滚失败: {e!s}", "ENHANCED_ROLLBACK_FAILED")
            return False

    def rollback_migration(self, migration_id: str) -> bool:
        try:
            backup_file = str(Path(self.backup_dir) / f"{migration_id}_backup.json")
            if not Path(backup_file).exists():
                raise ConfigException(f"找不到迁移备份文件: {backup_file}")

            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)

            config_data = backup_data.get("config_manager_data", {})
            if config_data:
                self.config_manager.clear_cache()
                for key, value in config_data.items():
                    self.config_manager.set(key, value)

            for migration_log in self.migration_logs:
                if migration_log.migration_id == migration_id:
                    migration_log.status = MigrationStatus.ROLLED_BACK
                    migration_log.completed_at = self.utc_now()
                    break

            return True

        except Exception as e:
            logger.error(f"回滚迁移失败: {e}")
            return False

    def _partial_rollback(self, migration_id: str) -> bool:
        try:
            failed_events = self.tracker.get_migration_events(migration_id, [MigrationEventType.ERROR_OCCURRED])

            failed_configs = set()
            for event in failed_events:
                if event.config_key:
                    failed_configs.add(event.config_key)

            if not failed_configs:
                return True

            rollback_operations = []
            for operation in reversed(self.state.rollback_stack):
                op_migration_id, key, old_value, new_value = operation
                if op_migration_id == migration_id and key in failed_configs:
                    rollback_operations.append((key, old_value))

            for key, old_value in rollback_operations:
                try:
                    if old_value is None:
                        pass
                    else:
                        self.config_manager.set(key, old_value)
                    self.tracker.record_config_migration(migration_id, key, None, old_value, "partial_rollback")
                except Exception as e:
                    logger.exception("操作失败")
                    self.tracker.record_error(
                        migration_id,
                        f"部分回滚配置项 {key} 失败: {e!s}",
                        "PARTIAL_ROLLBACK_CONFIG_FAILED",
                        config_key=key,
                    )

            return True

        except Exception as e:
            logger.exception("操作失败")
            self.tracker.record_error(migration_id, f"部分回滚失败: {e!s}", "PARTIAL_ROLLBACK_FAILED")
            return False

    def _config_only_rollback(self, migration_id: str) -> bool:
        try:
            backup_file = str(Path(self.backup_dir) / f"{migration_id}_backup.json")
            if not Path(backup_file).exists():
                raise ConfigException(f"找不到迁移备份文件: {backup_file}")

            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)

            config_data = backup_data.get("config_manager_data", {})
            if config_data:
                self.config_manager.clear_cache()
                for key, value in config_data.items():
                    self.config_manager.set(key, value)
                    self.tracker.record_config_migration(migration_id, key, None, value, "config_only_rollback")

            return True

        except Exception as e:
            logger.exception("操作失败")
            self.tracker.record_error(migration_id, f"仅配置回滚失败: {e!s}", "CONFIG_ONLY_ROLLBACK_FAILED")
            return False

    def validate_rollback_integrity(self, migration_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "migration_id": migration_id,
            "is_valid": True,
            "issues": [],
            "rollback_available": False,
            "backup_files": [],
            "rollback_points": [],
        }

        try:
            backup_file = str(Path(self.backup_dir) / f"{migration_id}_backup.json")
            if Path(backup_file).exists():
                result["rollback_available"] = True
                result["backup_files"].append(backup_file)

                try:
                    with open(backup_file, encoding="utf-8") as f:
                        backup_data = json.load(f)

                    required_keys = ["backup_time", "django_settings", "config_manager_data"]
                    for key in required_keys:
                        if key not in backup_data:
                            result["issues"].append(f"备份文件缺少必需字段: {key}")
                            result["is_valid"] = False
                except Exception as e:
                    # 静默处理:文件操作失败不影响主流程
                    # 静默处理:文件操作失败不影响主流程
                    result["issues"].append(f"备份文件损坏: {e!s}")
                    result["is_valid"] = False

            for point_file in Path(self.backup_dir).glob(f"{migration_id}_*_rollback_point.json"):
                result["rollback_points"].append(str(point_file))

            if not result["backup_files"] and not result["rollback_points"]:
                result["issues"].append("未找到任何回滚相关文件")
                result["is_valid"] = False

        except Exception as e:
            logger.exception("操作失败")
            result["issues"].append(f"验证回滚完整性失败: {e!s}")
            result["is_valid"] = False

        return result
