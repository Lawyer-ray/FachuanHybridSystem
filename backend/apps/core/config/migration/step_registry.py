"""Module for step registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class MigratorStepHandler(Protocol):
    def __call__(self) -> None: ...


@dataclass(frozen=True)
class MigratorStepDef:
    name: str
    description: str
    handler_attr: str


DEFAULT_MIGRATOR_STEPS: tuple[MigratorStepDef, ...] = (
    MigratorStepDef("backup_current_config", "备份当前配置", "_backup_current_config"),
    MigratorStepDef("analyze_django_settings", "分析 Django Settings", "_analyze_django_settings"),
    MigratorStepDef("create_config_schema", "创建配置模式", "_create_config_schema"),
    MigratorStepDef("migrate_core_configs", "迁移核心配置", "_migrate_core_configs"),
    MigratorStepDef("migrate_service_configs", "迁移服务配置", "_migrate_service_configs"),
    MigratorStepDef("migrate_business_configs", "迁移业务配置", "_migrate_business_configs"),
    MigratorStepDef("validate_migrated_config", "验证迁移后的配置", "_validate_migrated_config"),
    MigratorStepDef("create_compatibility_layer", "创建兼容层", "_create_compatibility_layer"),
)


def iter_step_defs() -> Iterable[MigratorStepDef]:
    return DEFAULT_MIGRATOR_STEPS
