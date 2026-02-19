"""
配置迁移器

负责将现有的 Django settings 配置迁移到统一配置管理系统，
提供向后兼容接口和迁移状态跟踪功能。
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from ._compatibility_layer import DjangoSettingsCompatibilityLayer
from ._migration_models import MigrationLog, MigrationStatus, MigrationStep
from ._migrator_rollback_mixin import ConfigMigratorRollbackMixin
from ._migrator_schema_mixin import ConfigMigratorSchemaMixin
from .exceptions import ConfigException
from .manager import ConfigManager
from .migration_tracker import MigrationStateTracker

logger = logging.getLogger("apps.core")

# 公开导出（保持向后兼容）
__all__ = [
    "ConfigMigrator",
    "DjangoSettingsCompatibilityLayer",
    "MigrationLog",
    "MigrationStatus",
    "MigrationStep",
]


class ConfigMigrator(ConfigMigratorRollbackMixin, ConfigMigratorSchemaMixin):
    """配置迁移器"""

    _STEP_HANDLERS: dict[str, str] = {
        "backup_current_config": "_backup_current_config",
        "analyze_django_settings": "_analyze_django_settings",
        "create_config_schema": "_create_config_schema",
        "migrate_core_configs": "_migrate_core_configs",
        "migrate_service_configs": "_migrate_service_configs",
        "migrate_business_configs": "_migrate_business_configs",
        "validate_migrated_config": "_validate_migrated_config",
        "create_compatibility_layer": "_create_compatibility_layer",
    }

    def __init__(
        self,
        config_manager: ConfigManager,
        backup_dir: str | None = None,
        enable_auto_rollback: bool = True,
    ) -> None:
        self._config_manager = config_manager
        self.backup_dir = backup_dir or self._get_default_backup_dir()
        self._compatibility_layer = DjangoSettingsCompatibilityLayer(config_manager)
        self._migration_logs: list[MigrationLog] = []
        self._current_migration: MigrationLog | None = None
        self.enable_auto_rollback = enable_auto_rollback
        self._tracker = MigrationStateTracker(
            db_path=os.path.join(self.backup_dir, "migration_tracker.db"),
            log_file=os.path.join(self.backup_dir, "migration.log"),
        )
        self._rollback_points: dict[str, dict[str, Any]] = {}
        self._rollback_stack: list[tuple[str, str, Any, Any]] = []
        os.makedirs(self.backup_dir, exist_ok=True)

    @property
    def config_manager(self) -> ConfigManager:
        return self._config_manager

    @property
    def compatibility_layer(self) -> DjangoSettingsCompatibilityLayer:
        return self._compatibility_layer

    @property
    def tracker(self) -> MigrationStateTracker:
        return self._tracker

    def _get_default_backup_dir(self) -> str:
        return os.path.join(os.getcwd(), ".config_migration_backups")

    def start_migration(self, migration_id: str | None = None) -> str:
        """开始配置迁移"""
        if self._current_migration and self._current_migration.status == MigrationStatus.IN_PROGRESS:
            raise ConfigException("已有迁移正在进行中")
        if migration_id is None:
            migration_id = datetime.now().strftime("migration_%Y%m%d_%H%M%S")
        self._current_migration = MigrationLog(
            migration_id=migration_id, started_at=datetime.now(), status=MigrationStatus.IN_PROGRESS
        )
        self._current_migration.steps = [
            MigrationStep("backup_current_config", "备份当前配置"),
            MigrationStep("analyze_django_settings", "分析 Django Settings"),
            MigrationStep("create_config_schema", "创建配置模式"),
            MigrationStep("migrate_core_configs", "迁移核心配置"),
            MigrationStep("migrate_service_configs", "迁移服务配置"),
            MigrationStep("migrate_business_configs", "迁移业务配置"),
            MigrationStep("validate_migrated_config", "验证迁移后的配置"),
            MigrationStep("create_compatibility_layer", "创建兼容层"),
        ]
        self._migration_logs.append(self._current_migration)
        return migration_id

    def execute_migration(self) -> bool:
        """执行配置迁移"""
        if not self._current_migration:
            raise ConfigException("未开始迁移，请先调用 start_migration()")
        migration_id = self._current_migration.migration_id
        try:
            self.tracker.start_migration(
                migration_id, len(self._current_migration.steps), self._current_migration.total_configs
            )
            self.create_rollback_point(migration_id, "migration_start")
            for step in self._current_migration.steps:
                self._execute_single_step(step, migration_id)
            self._current_migration.status = MigrationStatus.COMPLETED
            self._current_migration.completed_at = datetime.now()
            self._current_migration.rollback_available = True
            self.tracker.complete_migration(migration_id, self._current_migration.migrated_configs)
            self._save_migration_log()
            return True
        except Exception as e:
            self._current_migration.status = MigrationStatus.FAILED
            self._current_migration.error_message = str(e)
            self._current_migration.completed_at = datetime.now()
            self.tracker.fail_migration(migration_id, str(e))
            self._save_migration_log()
            return False

    def _execute_single_step(self, step: MigrationStep, migration_id: str) -> None:
        """执行单个迁移步骤"""
        step.start()
        self.tracker.start_step(migration_id, step.name, step.description)
        try:
            handler_name = self._STEP_HANDLERS.get(step.name)
            if handler_name:
                getattr(self, handler_name)()
            step.complete()
            self.tracker.complete_step(migration_id, step.name)
        except Exception as e:
            step.fail(str(e))
            self.tracker.fail_step(migration_id, step.name, str(e))
            if self.enable_auto_rollback:
                self.auto_rollback_on_error(migration_id, e)
            raise

    def _save_migration_log(self) -> None:
        if not self._current_migration:
            return
        log_file = os.path.join(self.backup_dir, f"{self._current_migration.migration_id}_log.json")
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self._current_migration.to_dict(), f, ensure_ascii=False, indent=2)

    def get_migration_status(self, migration_id: str | None = None) -> MigrationLog | None:
        if migration_id is None:
            return self._current_migration
        return next((m for m in self._migration_logs if m.migration_id == migration_id), None)

    def list_migrations(self) -> list[MigrationLog]:
        return self._migration_logs.copy()

    def get_compatibility_layer(self) -> DjangoSettingsCompatibilityLayer:
        return self.compatibility_layer

    def is_migration_needed(self) -> bool:
        for migration_log in self._migration_logs:
            if migration_log.status == MigrationStatus.COMPLETED:
                return False
        return len(self.compatibility_layer.get_all_django_configs()) > 0

    def generate_migration_report(self, migration_id: str) -> dict[str, Any]:
        migration_log = self.get_migration_status(migration_id)
        if not migration_log:
            raise ConfigException(f"找不到迁移: {migration_id}")
        report: dict[str, Any] = {
            "migration_summary": migration_log.to_dict(),
            "migration_statistics": {
                "total_steps": len(migration_log.steps),
                "completed_steps": len([s for s in migration_log.steps if s.status == MigrationStatus.COMPLETED]),
                "failed_steps": len([s for s in migration_log.steps if s.status == MigrationStatus.FAILED]),
                "success_rate": 0.0,
            },
            "recommendations": [],
        }
        if migration_log.steps:
            completed_count = len([s for s in migration_log.steps if s.status == MigrationStatus.COMPLETED])
            report["migration_statistics"]["success_rate"] = completed_count / len(migration_log.steps) * 100
        if migration_log.status == MigrationStatus.COMPLETED:
            report["recommendations"].append("迁移成功完成，建议进行全面测试")
            report["recommendations"].append("可以考虑清理旧的 Django settings 配置")
        elif migration_log.status == MigrationStatus.FAILED:
            report["recommendations"].append("迁移失败，建议检查错误日志并修复问题")
            report["recommendations"].append("可以尝试回滚到迁移前状态")
        return report
