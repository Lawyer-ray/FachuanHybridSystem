"""Module for rollback validation."""

from __future__ import annotations

"""
回滚验证模块

负责验证回滚完整性和列出回滚选项.
从 rollback_migrator.py 中拆分出来.
"""


import json
import logging
import os
from typing import Any

from .manager import ConfigManager
from .migration_tracker import MigrationEventType, MigrationStateTracker

logger = logging.getLogger(__name__)


def validate_rollback_integrity(
    migration_id: str,
    backup_dir: str,
    rollback_points: dict[str, dict[str, Any]],
    rollback_stack: list[tuple[str, str, Any, Any]],
    tracker: MigrationStateTracker,
) -> dict[str, Any]:
    """
    验证回滚完整性

    Args:
        migration_id: 迁移ID
        backup_dir: 备份目录
        rollback_points: 回滚点字典
        rollback_stack: 回滚栈
        tracker: 状态跟踪器

    Returns:
        dict[str, Any]: 验证结果
    """
    result: dict[str, Any] = {
        "migration_id": migration_id,
        "is_valid": True,
        "issues": [],
        "rollback_available": False,
        "backup_files": [],
        "rollback_points": [],
    }

    try:
        _validate_backup_file(migration_id, backup_dir, result)
        _validate_rollback_points_data(migration_id, rollback_points, rollback_stack, result)
        _validate_migration_progress(migration_id, tracker, result)
    except Exception as e:
        logger.exception("操作失败")
        result["issues"].append(f"验证过程中发生错误: {e!s}")
        result["is_valid"] = False

    return result


def _validate_backup_file(migration_id: str, backup_dir: str, result: dict[str, Any]) -> None:
    """验证备份文件完整性"""
    backup_file = os.path.join(backup_dir, f"{migration_id}_backup.json")
    if not os.path.exists(backup_file):
        result["issues"].append("找不到备份文件")
        result["is_valid"] = False
        return

    result["rollback_available"] = True
    result["backup_files"].append(backup_file)

    try:
        with open(backup_file, encoding="utf-8") as f:
            backup_data = json.load(f)

        for key in ["backup_time", "django_settings", "config_manager_data"]:
            if key not in backup_data:
                result["issues"].append(f"备份文件缺少必需字段: {key}")
                result["is_valid"] = False
    except Exception as e:
        logger.exception("操作失败")
        result["issues"].append(f"备份文件损坏: {e!s}")
        result["is_valid"] = False


def _validate_rollback_points_data(
    migration_id: str,
    rollback_points: dict[str, dict[str, Any]],
    rollback_stack: list[tuple[str, str, Any, Any]],
    result: dict[str, Any],
) -> None:
    """验证回滚点和回滚栈"""
    for _point_key, rollback_point in rollback_points.items():
        if rollback_point["migration_id"] == migration_id:
            result["rollback_points"].append(rollback_point["point_name"])

    rollback_operations = [op for op in rollback_stack if op[0] == migration_id]
    if rollback_operations:
        result["rollback_operations_count"] = len(rollback_operations)
    else:
        result["issues"].append("没有可用的回滚操作")


def _validate_migration_progress(
    migration_id: str,
    tracker: MigrationStateTracker,
    result: dict[str, Any],
) -> None:
    """验证迁移进度状态"""
    migration_progress = tracker.get_migration_progress(migration_id)
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


def list_rollback_options(
    migration_id: str,
    backup_dir: str,
    rollback_points: dict[str, dict[str, Any]],
    rollback_stack: list[tuple[str, str, Any, Any]],
    tracker: MigrationStateTracker,
) -> dict[str, Any]:
    """
    列出回滚选项

    Args:
        migration_id: 迁移ID
        backup_dir: 备份目录
        rollback_points: 回滚点字典
        rollback_stack: 回滚栈
        tracker: 状态跟踪器

    Returns:
        dict[str, Any]: 回滚选项
    """
    options: dict[str, Any] = {
        "migration_id": migration_id,
        "available_strategies": [],
        "rollback_points": [],
        "backup_files": [],
        "recommended_strategy": None,
    }

    validation_result = validate_rollback_integrity(migration_id, backup_dir, rollback_points, rollback_stack, tracker)

    if validation_result["rollback_available"]:
        options["available_strategies"].append(
            {"name": "full", "description": "完整回滚:恢复所有配置到迁移前状态", "risk_level": "low"}
        )
        options["available_strategies"].append(
            {"name": "config_only", "description": "仅配置回滚:只回滚配置管理器中的配置", "risk_level": "medium"}
        )

    failed_events = tracker.get_migration_events(migration_id, [MigrationEventType.ERROR_OCCURRED])

    if failed_events:
        options["available_strategies"].append(
            {"name": "partial", "description": "部分回滚:只回滚失败的配置项", "risk_level": "low"}
        )

    options["rollback_points"] = validation_result["rollback_points"]
    options["backup_files"] = validation_result["backup_files"]

    if failed_events and len(failed_events) < 5:
        options["recommended_strategy"] = "partial"
    elif validation_result["rollback_available"]:
        options["recommended_strategy"] = "full"
    else:
        options["recommended_strategy"] = None

    return options


def partial_rollback(
    migration_id: str,
    config_manager: ConfigManager,
    rollback_stack: list[tuple[str, str, Any, Any]],
    tracker: MigrationStateTracker,
) -> bool:
    """部分回滚:只回滚失败的配置项"""
    try:
        failed_events = tracker.get_migration_events(migration_id, [MigrationEventType.ERROR_OCCURRED])

        failed_configs = set()
        for event in failed_events:
            if event.config_key:
                failed_configs.add(event.config_key)

        if not failed_configs:
            return True

        rollback_operations = []
        for operation in reversed(rollback_stack):
            op_migration_id, key, old_value, _new_value = operation
            if op_migration_id == migration_id and key in failed_configs:
                rollback_operations.append((key, old_value))

        for key, old_value in rollback_operations:
            try:
                if old_value is not None:
                    config_manager.set(key, old_value)
                tracker.record_config_migration(migration_id, key, None, old_value, "partial_rollback")
            except Exception as e:
                logger.exception("操作失败")
                tracker.record_error(
                    migration_id,
                    f"部分回滚配置项 {key} 失败: {e!s}",
                    "PARTIAL_ROLLBACK_CONFIG_FAILED",
                    config_key=key,
                )

        return True

    except Exception as e:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"部分回滚失败: {e!s}", "PARTIAL_ROLLBACK_FAILED")
        return False


def config_only_rollback(
    migration_id: str,
    backup_dir: str,
    config_manager: ConfigManager,
    tracker: MigrationStateTracker,
) -> bool:
    """仅配置回滚:只回滚配置管理器中的配置"""
    import json
    import os

    from .exceptions import ConfigException

    try:
        backup_file = os.path.join(backup_dir, f"{migration_id}_backup.json")
        if not os.path.exists(backup_file):
            raise ConfigException(f"找不到迁移备份文件: {backup_file}")

        with open(backup_file, encoding="utf-8") as f:
            backup_data = json.load(f)

        config_data = backup_data.get("config_manager_data", {})
        if config_data:
            config_manager.clear_cache()
            for key, value in config_data.items():
                config_manager.set(key, value)
                tracker.record_config_migration(migration_id, key, None, value, "config_only_rollback")

        return True

    except Exception as e:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"仅配置回滚失败: {e!s}", "CONFIG_ONLY_ROLLBACK_FAILED")
        return False
