"""Module for data migrator."""

from __future__ import annotations

"""
数据迁移器

负责将 Django settings 中的配置数据迁移到统一配置管理系统,
包括核心配置、服务配置和业务配置的迁移.
"""


from typing import Any

from .manager import ConfigManager
from .migrator_models import MigrationLog
from .schema_migrator import DjangoSettingsCompatibilityLayer


def migrate_core_configs(
    compatibility_layer: DjangoSettingsCompatibilityLayer,
    config_manager: ConfigManager,
    current_migration: MigrationLog,
    rollback_stack: list[tuple[str, str, Any, Any]],
    migration_id: str,
) -> None:
    """迁移核心配置"""

    django_configs = compatibility_layer.get_all_django_configs()
    migrated_count = 0

    # Django 核心配置映射
    core_mappings = {
        "SECRET_KEY": "django.secret_key",
        "DEBUG": "django.debug",
        "ALLOWED_HOSTS": "django.allowed_hosts",
        "LANGUAGE_CODE": "django.language_code",
        "TIME_ZONE": "django.time_zone",
    }

    for django_key, config_key in core_mappings.items():
        if django_key in django_configs:
            value = django_configs[django_key]
            old_value = config_manager.get(config_key) if config_manager.has(config_key) else None
            config_manager.set(config_key, value)
            rollback_stack.append((migration_id, config_key, old_value, value))
            migrated_count += 1

    # 数据库配置特殊处理
    if "DATABASES" in django_configs:
        databases = django_configs["DATABASES"]
        if "default" in databases:
            db_config = databases["default"]

            db_fields = [
                ("database.engine", "ENGINE", None),
                ("database.name", "NAME", None),
                ("database.host", "HOST", "localhost"),
                ("database.port", "PORT", 3306),
            ]

            for config_key, db_key, default in db_fields:
                old_value = config_manager.get(config_key) if config_manager.has(config_key) else None
                new_value = db_config.get(db_key, default) if default is not None else db_config.get(db_key)
                config_manager.set(config_key, new_value)
                rollback_stack.append((migration_id, config_key, old_value, new_value))

            migrated_count += 1

    current_migration.migrated_configs += migrated_count


def migrate_service_configs(
    compatibility_layer: DjangoSettingsCompatibilityLayer,
    config_manager: ConfigManager,
    current_migration: MigrationLog,
    rollback_stack: list[tuple[str, str, Any, Any]],
    migration_id: str,
) -> None:
    """迁移服务配置"""
    django_configs = compatibility_layer.get_all_django_configs()
    migrated_count = 0

    # Moonshot 配置
    for django_key, config_key in [
        ("MOONSHOT_BASE_URL", "services.moonshot.base_url"),
        ("MOONSHOT_API_KEY", "services.moonshot.api_key"),
    ]:
        if django_key in django_configs:
            old_value = config_manager.get(config_key) if config_manager.has(config_key) else None
            new_value = django_configs[django_key]
            config_manager.set(config_key, new_value)
            rollback_stack.append((migration_id, config_key, old_value, new_value))
            migrated_count += 1

    # Ollama 配置
    if "OLLAMA" in django_configs:
        ollama_config = django_configs["OLLAMA"]
        if isinstance(ollama_config, dict):
            for ollama_key, config_suffix in [("MODEL", "model"), ("BASE_URL", "base_url")]:
                if ollama_key in ollama_config:
                    config_key = f"services.ollama.{config_suffix}"
                    old_value = config_manager.get(config_key) if config_manager.has(config_key) else None
                    new_value = ollama_config[ollama_key]
                    config_manager.set(config_key, new_value)
                    rollback_stack.append((migration_id, config_key, old_value, new_value))

            migrated_count += 1

    current_migration.migrated_configs += migrated_count


def migrate_business_configs(
    compatibility_layer: DjangoSettingsCompatibilityLayer,
    config_manager: ConfigManager,
    current_migration: MigrationLog,
    rollback_stack: list[tuple[str, str, Any, Any]],
    migration_id: str,
) -> None:
    """迁移业务配置"""
    django_configs = compatibility_layer.get_all_django_configs()
    migrated_count = 0

    # 按配置组迁移
    config_groups = [
        ("FEISHU", "chat_platforms.feishu"),
        ("CASE_CHAT", "features.case_chat"),
        ("COURT_SMS_PROCESSING", "features.court_sms"),
    ]

    for django_key, config_prefix in config_groups:
        if django_key in django_configs:
            group_config = django_configs[django_key]
            if isinstance(group_config, dict):
                for key, value in group_config.items():
                    config_key = f"{config_prefix}.{key.lower()}"
                    old_value = config_manager.get(config_key) if config_manager.has(config_key) else None
                    config_manager.set(config_key, value)
                    rollback_stack.append((migration_id, config_key, old_value, value))
                migrated_count += 1

    current_migration.migrated_configs += migrated_count
