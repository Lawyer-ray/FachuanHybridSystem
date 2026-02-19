"""配置迁移器 — 回滚相关 Mixin"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from .exceptions import ConfigException
from ._migration_models import MigrationLog, MigrationStatus

logger = logging.getLogger("apps.core")


class ConfigMigratorRollbackMixin:
    """回滚相关方法"""

    backup_dir: str
    enable_auto_rollback: bool
    _migration_logs: list[MigrationLog]
    _rollback_points: dict[str, dict[str, Any]]
    _rollback_stack: list[tuple[str, str, Any, Any]]

    # 子类提供
    @property
    def config_manager(self) -> Any: ...  # type: ignore[misc]
    @property
    def compatibility_layer(self) -> Any: ...  # type: ignore[misc]
    @property
    def tracker(self) -> Any: ...  # type: ignore[misc]

    def _save_migration_log(self) -> None: ...

    def rollback_migration(self, migration_id: str) -> bool:
        """回滚迁移（从备份文件恢复）"""
        try:
            backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
            if not os.path.exists(backup_file):
                raise ConfigException(f"找不到迁移备份文件: {backup_file}")
            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)
            config_data = backup_data.get("config_manager_data", {})
            if config_data:
                self.config_manager.clear_cache()
                for key, value in config_data.items():
                    self.config_manager.set(key, value)
            for migration_log in self._migration_logs:
                if migration_log.migration_id == migration_id:
                    migration_log.status = MigrationStatus.ROLLED_BACK
                    migration_log.completed_at = datetime.now()
                    self._save_migration_log()
                    break
            return True
        except Exception as e:
            logger.error(f"回滚迁移失败: {e}")
            return False

    def create_rollback_point(self, migration_id: str, point_name: str) -> None:
        """创建回滚点"""
        rollback_point: dict[str, Any] = {
            "migration_id": migration_id,
            "point_name": point_name,
            "timestamp": datetime.now().isoformat(),
            "config_state": self.config_manager.get_all() if self.config_manager.is_loaded() else {},
            "django_state": self.compatibility_layer.get_all_django_configs(),
            "rollback_stack": self._rollback_stack.copy(),
        }
        point_key = f"{migration_id}_{point_name}"
        self._rollback_points[point_key] = rollback_point
        rollback_file = os.path.join(self.backup_dir, f"{point_key}_rollback_point.json")
        with open(rollback_file, "w", encoding="utf-8") as f:
            json.dump(rollback_point, f, ensure_ascii=False, indent=2, default=str)
        self.tracker.record_config_migration(
            migration_id, f"rollback_point_{point_name}", None, point_name, "rollback_point"
        )

    def rollback_to_point(self, migration_id: str, point_name: str) -> bool:
        """回滚到指定回滚点"""
        try:
            point_key = f"{migration_id}_{point_name}"
            rollback_point: dict[str, Any] | None = self._rollback_points.get(point_key)
            if not rollback_point:
                rollback_file = os.path.join(self.backup_dir, f"{point_key}_rollback_point.json")
                if os.path.exists(rollback_file):
                    with open(rollback_file, encoding="utf-8") as f:
                        rollback_point = json.load(f)
                else:
                    raise ConfigException(f"找不到回滚点: {point_name}")
            self.tracker.record_error(migration_id, f"开始回滚到回滚点: {point_name}", "ROLLBACK_STARTED")
            if rollback_point is not None:
                config_state = rollback_point.get("config_state", {})
                if config_state:
                    self.config_manager.clear_cache()
                    for key, value in config_state.items():
                        self.config_manager.set(key, value)
                self._rollback_stack = rollback_point.get("rollback_stack", [])
            self.tracker.record_config_migration(
                migration_id, f"rollback_completed_{point_name}", None, point_name, "rollback"
            )
            return True
        except Exception as e:
            self.tracker.record_error(migration_id, f"回滚失败: {e!s}", "ROLLBACK_FAILED")
            return False

    def auto_rollback_on_error(self, migration_id: str, error: Exception) -> bool:
        """错误时自动回滚"""
        if not self.enable_auto_rollback:
            return False
        try:
            self.tracker.record_error(migration_id, f"触发自动回滚: {error!s}", "AUTO_ROLLBACK_TRIGGERED")
            success = self._execute_rollback_operations(migration_id)
            if success:
                for migration_log in self._migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = datetime.now()
                        migration_log.error_message = f"自动回滚: {error!s}"
                        break
                self.tracker.record_config_migration(
                    migration_id, "auto_rollback_success", None, "success", "auto_rollback"
                )
            else:
                self.tracker.record_error(migration_id, "自动回滚失败", "AUTO_ROLLBACK_FAILED")
            return success
        except Exception as rollback_error:
            self.tracker.record_error(
                migration_id, f"自动回滚过程中发生错误: {rollback_error!s}", "AUTO_ROLLBACK_ERROR"
            )
            return False

    def _execute_rollback_operations(self, migration_id: str) -> bool:
        """执行回滚操作"""
        try:
            rollback_operations = [
                (key, old_value)
                for op_migration_id, key, old_value, new_value in reversed(self._rollback_stack)
                if op_migration_id == migration_id
            ]
            for key, old_value in rollback_operations:
                try:
                    if old_value is not None:
                        self.config_manager.set(key, old_value)
                    self.tracker.record_config_migration(migration_id, key, None, old_value, "rollback")
                except Exception as e:
                    self.tracker.record_error(
                        migration_id, f"回滚配置项 {key} 失败: {e!s}", "ROLLBACK_CONFIG_FAILED", config_key=key
                    )
            self._rollback_stack = [op for op in self._rollback_stack if op[0] != migration_id]
            return True
        except Exception as e:
            self.tracker.record_error(migration_id, f"执行回滚操作失败: {e!s}", "EXECUTE_ROLLBACK_FAILED")
            return False

    def _track_config_change(self, migration_id: str, key: str, old_value: Any, new_value: Any) -> None:
        """跟踪配置变更（用于回滚）"""
        self._rollback_stack.append((migration_id, key, old_value, new_value))
        self.tracker.record_config_migration(migration_id, key, old_value, new_value)

    def enhanced_rollback_migration(self, migration_id: str, rollback_strategy: str = "full") -> bool:
        """增强的迁移回滚"""
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
                for migration_log in self._migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = datetime.now()
                        break
                self.tracker.record_config_migration(
                    migration_id, f"enhanced_rollback_success_{rollback_strategy}", None, "success", "enhanced_rollback"
                )
            return success
        except Exception as e:
            self.tracker.record_error(migration_id, f"增强回滚失败: {e!s}", "ENHANCED_ROLLBACK_FAILED")
            return False

    def _partial_rollback(self, migration_id: str) -> bool:
        """部分回滚：只回滚失败的配置项"""
        from .migration_tracker import MigrationEventType
        try:
            failed_events = self.tracker.get_migration_events(migration_id, [MigrationEventType.ERROR_OCCURRED])
            failed_configs = {event.config_key for event in failed_events if event.config_key}
            if not failed_configs:
                return True
            rollback_operations = [
                (key, old_value)
                for op_migration_id, key, old_value, _ in reversed(self._rollback_stack)
                if op_migration_id == migration_id and key in failed_configs
            ]
            for key, old_value in rollback_operations:
                try:
                    if old_value is not None:
                        self.config_manager.set(key, old_value)
                    self.tracker.record_config_migration(migration_id, key, None, old_value, "partial_rollback")
                except Exception as e:
                    self.tracker.record_error(
                        migration_id, f"部分回滚配置项 {key} 失败: {e!s}",
                        "PARTIAL_ROLLBACK_CONFIG_FAILED", config_key=key,
                    )
            return True
        except Exception as e:
            self.tracker.record_error(migration_id, f"部分回滚失败: {e!s}", "PARTIAL_ROLLBACK_FAILED")
            return False

    def _config_only_rollback(self, migration_id: str) -> bool:
        """仅配置回滚"""
        try:
            backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
            if not os.path.exists(backup_file):
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
            self.tracker.record_error(migration_id, f"仅配置回滚失败: {e!s}", "CONFIG_ONLY_ROLLBACK_FAILED")
            return False

    def validate_rollback_integrity(self, migration_id: str) -> dict[str, Any]:
        """验证回滚完整性"""
        result: dict[str, Any] = {
            "migration_id": migration_id,
            "is_valid": True,
            "issues": [],
            "rollback_available": False,
            "backup_files": [],
            "rollback_points": [],
        }
        try:
            self._check_backup_file(migration_id, result)
            self._collect_rollback_points(migration_id, result)
            self._check_rollback_stack(migration_id, result)
            self._check_migration_status(migration_id, result)
        except Exception as e:
            result["issues"].append(f"验证过程中发生错误: {e!s}")
            result["is_valid"] = False
        return result

    def _check_backup_file(self, migration_id: str, result: dict[str, Any]) -> None:
        backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
        if not os.path.exists(backup_file):
            result["issues"].append("找不到备份文件")
            result["is_valid"] = False
            return
        result["rollback_available"] = True
        result["backup_files"].append(backup_file)
        try:
            with open(backup_file, encoding="utf-8") as f:
                backup_data = json.load(f)
            for key in ("backup_time", "django_settings", "config_manager_data"):
                if key not in backup_data:
                    result["issues"].append(f"备份文件缺少必需字段: {key}")
                    result["is_valid"] = False
        except Exception as e:
            result["issues"].append(f"备份文件损坏: {e!s}")
            result["is_valid"] = False

    def _collect_rollback_points(self, migration_id: str, result: dict[str, Any]) -> None:
        for _point_key, rollback_point in self._rollback_points.items():
            if rollback_point["migration_id"] == migration_id:
                result["rollback_points"].append(rollback_point["point_name"])

    def _check_rollback_stack(self, migration_id: str, result: dict[str, Any]) -> None:
        rollback_operations = [op for op in self._rollback_stack if op[0] == migration_id]
        if rollback_operations:
            result["rollback_operations_count"] = len(rollback_operations)
        else:
            result["issues"].append("没有可用的回滚操作")

    def _check_migration_status(self, migration_id: str, result: dict[str, Any]) -> None:
        migration_progress = self.tracker.get_migration_progress(migration_id)
        if not migration_progress:
            result["issues"].append("找不到迁移进度信息")
            result["is_valid"] = False
            return
        if migration_progress.is_failed:
            result["migration_status"] = "failed"
        elif migration_progress.is_completed:
            result["migration_status"] = "completed"
        else:
            result["migration_status"] = "in_progress"

    def list_rollback_options(self, migration_id: str) -> dict[str, Any]:
        """列出回滚选项"""
        from .migration_tracker import MigrationEventType
        options: dict[str, Any] = {
            "migration_id": migration_id,
            "available_strategies": [],
            "rollback_points": [],
            "backup_files": [],
            "recommended_strategy": None,
        }
        validation_result = self.validate_rollback_integrity(migration_id)
        if validation_result["rollback_available"]:
            options["available_strategies"].append(
                {"name": "full", "description": "完整回滚：恢复所有配置到迁移前状态", "risk_level": "low"}
            )
            options["available_strategies"].append(
                {"name": "config_only", "description": "仅配置回滚：只回滚配置管理器中的配置", "risk_level": "medium"}
            )
        failed_events = self.tracker.get_migration_events(migration_id, [MigrationEventType.ERROR_OCCURRED])
        if failed_events:
            options["available_strategies"].append(
                {"name": "partial", "description": "部分回滚：只回滚失败的配置项", "risk_level": "low"}
            )
        options["rollback_points"] = validation_result["rollback_points"]
        options["backup_files"] = validation_result["backup_files"]
        if failed_events and len(failed_events) < 5:
            options["recommended_strategy"] = "partial"
        elif validation_result["rollback_available"]:
            options["recommended_strategy"] = "full"
        return options
