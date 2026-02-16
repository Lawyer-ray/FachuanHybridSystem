"""Module for rollback migrator."""

from __future__ import annotations

"""
回滚迁移器

负责配置迁移的回滚操作,包括完整回滚、部分回滚、
仅配置回滚,以及回滚完整性验证.
"""


import json
import logging
import os
from typing import Any

from .exceptions import ConfigException
from .manager import ConfigManager
from .migration_tracker import MigrationStateTracker
from .migrator_models import MigrationLog, MigrationStatus
from .rollback_validation import config_only_rollback as _config_only_rollback
from .rollback_validation import list_rollback_options
from .rollback_validation import partial_rollback as _partial_rollback
from .rollback_validation import validate_rollback_integrity
from .schema_migrator import DjangoSettingsCompatibilityLayer

logger = logging.getLogger(__name__)


def rollback_migration(
    migration_id: str,
    backup_dir: str,
    config_manager: ConfigManager,
    migration_logs: list[MigrationLog],
    save_log_fn: Any,
) -> bool:
    """
    回滚迁移

    Args:
        migration_id: 迁移ID
        backup_dir: 备份目录
        config_manager: 配置管理器
        migration_logs: 迁移日志列表
        save_log_fn: 保存日志的回调函数

    Returns:
        bool: 是否成功回滚
    """
    try:
        from datetime import datetime

        # 查找备份文件
        backup_file = os.path.join(backup_dir, f"{migration_id}_backup.json")
        if not os.path.exists(backup_file):
            raise ConfigException(f"找不到迁移备份文件: {backup_file}")

        # 加载备份数据
        with open(backup_file, encoding="utf-8") as f:
            backup_data = json.load(f)

        # 恢复配置管理器数据
        config_data = backup_data.get("config_manager_data", {})
        if config_data:
            config_manager.clear_cache()
            for key, value in config_data.items():
                config_manager.set(key, value)

        # 更新迁移状态
        for migration_log in migration_logs:
            if migration_log.migration_id == migration_id:
                migration_log.status = MigrationStatus.ROLLED_BACK
                migration_log.completed_at = datetime.now()
                save_log_fn()
                break

        return True

    except Exception as e:
        logger.error("回滚迁移失败: %s", e)
        return False


def create_rollback_point(
    migration_id: str,
    point_name: str,
    config_manager: ConfigManager,
    compatibility_layer: DjangoSettingsCompatibilityLayer,
    rollback_points: dict[str, dict[str, Any]],
    rollback_stack: list[tuple[str, str, Any, Any]],
    backup_dir: str,
    tracker: MigrationStateTracker,
) -> None:
    """
    创建回滚点

    Args:
        migration_id: 迁移ID
        point_name: 回滚点名称
        config_manager: 配置管理器
        compatibility_layer: 兼容层
        rollback_points: 回滚点字典
        rollback_stack: 回滚栈
        backup_dir: 备份目录
        tracker: 状态跟踪器
    """
    from datetime import datetime

    rollback_point = {
        "migration_id": migration_id,
        "point_name": point_name,
        "timestamp": datetime.now().isoformat(),
        "config_state": config_manager.get_all() if config_manager.is_loaded() else {},
        "django_state": compatibility_layer.get_all_django_configs(),
        "rollback_stack": rollback_stack.copy(),
    }

    point_key = f"{migration_id}_{point_name}"
    rollback_points[point_key] = rollback_point

    # 保存回滚点到文件
    rollback_file = os.path.join(backup_dir, f"{point_key}_rollback_point.json")
    with open(rollback_file, "w", encoding="utf-8") as f:
        json.dump(rollback_point, f, ensure_ascii=False, indent=2, default=str)

    # 记录事件
    tracker.record_config_migration(migration_id, f"rollback_point_{point_name}", None, point_name, "rollback_point")


def rollback_to_point(
    migration_id: str,
    point_name: str,
    config_manager: ConfigManager,
    rollback_points: dict[str, dict[str, Any]],
    rollback_stack: list[tuple[str, str, Any, Any]],
    backup_dir: str,
    tracker: MigrationStateTracker,
) -> bool:
    """
    回滚到指定回滚点

    Args:
        migration_id: 迁移ID
        point_name: 回滚点名称
        config_manager: 配置管理器
        rollback_points: 回滚点字典
        rollback_stack: 回滚栈(会被修改)
        backup_dir: 备份目录
        tracker: 状态跟踪器

    Returns:
        bool: 是否成功回滚
    """
    try:
        point_key = f"{migration_id}_{point_name}"

        # 从内存获取回滚点
        rollback_point = rollback_points.get(point_key)

        # 如果内存中没有,尝试从文件加载
        if not rollback_point:
            rollback_file = os.path.join(backup_dir, f"{point_key}_rollback_point.json")
            if os.path.exists(rollback_file):
                with open(rollback_file, encoding="utf-8") as f:
                    rollback_point = json.load(f)
            else:
                raise ConfigException(f"找不到回滚点: {point_name}")

        # 记录回滚开始
        tracker.record_error(migration_id, f"开始回滚到回滚点: {point_name}", "ROLLBACK_STARTED")

        # 恢复配置状态
        if rollback_point is None:
            raise ValueError("Rollback point cannot be None")
        config_state = rollback_point.get("config_state", {})
        if config_state:
            config_manager.clear_cache()
            for key, value in config_state.items():
                config_manager.set(key, value)

        # 恢复回滚栈
        rollback_stack.clear()
        rollback_stack.extend(rollback_point.get("rollback_stack", []))

        # 记录回滚完成
        tracker.record_config_migration(migration_id, f"rollback_completed_{point_name}", None, point_name, "rollback")

        return True

    except Exception as e:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"回滚失败: {e!s}", "ROLLBACK_FAILED")
        return False


def auto_rollback_on_error(
    migration_id: str,
    error: Exception,
    enable_auto_rollback: bool,
    config_manager: ConfigManager,
    migration_logs: list[MigrationLog],
    rollback_stack: list[tuple[str, str, Any, Any]],
    tracker: MigrationStateTracker,
) -> bool:
    """
    错误时自动回滚

    Args:
        migration_id: 迁移ID
        error: 错误异常
        enable_auto_rollback: 是否启用自动回滚
        config_manager: 配置管理器
        migration_logs: 迁移日志列表
        rollback_stack: 回滚栈
        tracker: 状态跟踪器

    Returns:
        bool: 是否成功回滚
    """
    from datetime import datetime

    if not enable_auto_rollback:
        return False

    try:
        tracker.record_error(migration_id, f"触发自动回滚: {error!s}", "AUTO_ROLLBACK_TRIGGERED")

        success = execute_rollback_operations(migration_id, config_manager, rollback_stack, tracker)

        if success:
            for migration_log in migration_logs:
                if migration_log.migration_id == migration_id:
                    migration_log.status = MigrationStatus.ROLLED_BACK
                    migration_log.completed_at = datetime.now()
                    migration_log.error_message = f"自动回滚: {error!s}"
                    break

            tracker.record_config_migration(migration_id, "auto_rollback_success", None, "success", "auto_rollback")
        else:
            tracker.record_error(migration_id, "自动回滚失败", "AUTO_ROLLBACK_FAILED")

        return success

    except Exception as rollback_error:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"自动回滚过程中发生错误: {rollback_error!s}", "AUTO_ROLLBACK_ERROR")
        return False


def execute_rollback_operations(
    migration_id: str,
    config_manager: ConfigManager,
    rollback_stack: list[tuple[str, str, Any, Any]],
    tracker: MigrationStateTracker,
) -> bool:
    """
    执行回滚操作

    Args:
        migration_id: 迁移ID
        config_manager: 配置管理器
        rollback_stack: 回滚栈
        tracker: 状态跟踪器

    Returns:
        bool: 是否成功
    """
    try:
        rollback_operations = []

        for operation in reversed(rollback_stack):
            op_migration_id, key, old_value, new_value = operation
            if op_migration_id == migration_id:
                rollback_operations.append((key, old_value))

        for key, old_value in rollback_operations:
            try:
                if old_value is None:
                    if config_manager.has(key):
                        pass
                else:
                    config_manager.set(key, old_value)

                tracker.record_config_migration(migration_id, key, None, old_value, "rollback")

            except Exception as e:
                logger.exception("操作失败")
                tracker.record_error(
                    migration_id, f"回滚配置项 {key} 失败: {e!s}", "ROLLBACK_CONFIG_FAILED", config_key=key
                )
                continue

        rollback_stack[:] = [op for op in rollback_stack if op[0] != migration_id]

        return True

    except Exception as e:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"执行回滚操作失败: {e!s}", "EXECUTE_ROLLBACK_FAILED")
        return False


def enhanced_rollback_migration(
    migration_id: str,
    rollback_strategy: str,
    config_manager: ConfigManager,
    migration_logs: list[MigrationLog],
    rollback_stack: list[tuple[str, str, Any, Any]],
    backup_dir: str,
    tracker: MigrationStateTracker,
    save_log_fn: Any,
) -> bool:
    """
    增强的迁移回滚

    Args:
        migration_id: 迁移ID
        rollback_strategy: 回滚策略 ('full', 'partial', 'config_only')
        config_manager: 配置管理器
        migration_logs: 迁移日志列表
        rollback_stack: 回滚栈
        backup_dir: 备份目录
        tracker: 状态跟踪器
        save_log_fn: 保存日志的回调函数

    Returns:
        bool: 是否成功回滚
    """
    from datetime import datetime

    try:
        tracker.record_error(migration_id, f"开始增强回滚 (策略: {rollback_strategy})", "ENHANCED_ROLLBACK_STARTED")

        if rollback_strategy == "full":
            success = rollback_migration(migration_id, backup_dir, config_manager, migration_logs, save_log_fn)
        elif rollback_strategy == "partial":
            success = _partial_rollback(migration_id, config_manager, rollback_stack, tracker)
        elif rollback_strategy == "config_only":
            success = _config_only_rollback(migration_id, backup_dir, config_manager, tracker)
        else:
            raise ConfigException(f"不支持的回滚策略: {rollback_strategy}")

        if success:
            for migration_log in migration_logs:
                if migration_log.migration_id == migration_id:
                    migration_log.status = MigrationStatus.ROLLED_BACK
                    migration_log.completed_at = datetime.now()
                    break

            tracker.record_config_migration(
                migration_id, f"enhanced_rollback_success_{rollback_strategy}", None, "success", "enhanced_rollback"
            )

        return success

    except Exception as e:
        logger.exception("操作失败")
        tracker.record_error(migration_id, f"增强回滚失败: {e!s}", "ENHANCED_ROLLBACK_FAILED")
        return False


# Re-export validation functions for backward compatibility
__all__: list[str] = [
    "auto_rollback_on_error",
    "create_rollback_point",
    "enhanced_rollback_migration",
    "execute_rollback_operations",
    "list_rollback_options",
    "rollback_migration",
    "rollback_to_point",
    "validate_rollback_integrity",
]
