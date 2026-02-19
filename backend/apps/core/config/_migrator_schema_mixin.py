"""配置迁移器 — Schema 注册和迁移方法 Mixin"""

import json
import logging
import os
from typing import Any

from ._migration_models import MigrationLog
from .exceptions import ConfigException, ConfigValidationError

logger = logging.getLogger("apps.core")


class ConfigMigratorSchemaMixin:
    """Schema 注册和配置迁移相关方法"""

    backup_dir: str
    _current_migration: MigrationLog | None

    # 子类提供
    @property
    def config_manager(self) -> Any: ...  # type: ignore[misc]
    @property
    def compatibility_layer(self) -> Any: ...  # type: ignore[misc]

    def _track_config_change(self, migration_id: str, key: str, old_value: Any, new_value: Any) -> None: ...

    def _is_sensitive_config_key(self, key: str) -> bool:
        sensitive_keywords = [
            "SECRET",
            "KEY",
            "PASSWORD",
            "TOKEN",
            "CREDENTIAL",
            "PRIVATE",
            "AUTH",
            "API_KEY",
            "ACCESS_KEY",
        ]
        return any(kw in key.upper() for kw in sensitive_keywords)

    def _backup_current_config(self) -> None:
        if self._current_migration is None:
            raise ConfigException("没有正在进行的迁移")
        backup_data = {
            "backup_time": __import__("datetime").datetime.now().isoformat(),
            "django_settings": self.compatibility_layer.get_all_django_configs(),
            "config_manager_data": self.config_manager.get_all() if self.config_manager.is_loaded() else {},
        }
        backup_file = os.path.join(self.backup_dir, f"{self._current_migration.migration_id}_backup.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

    def _analyze_django_settings(self) -> None:
        if self._current_migration is None:
            raise ConfigException("没有正在进行的迁移")
        django_configs = self.compatibility_layer.get_all_django_configs()
        self._current_migration.total_configs = len(django_configs)
        analysis: dict[str, Any] = {
            "total_configs": len(django_configs),
            "config_types": {},
            "sensitive_configs": [],
            "complex_configs": [],
        }
        for key, value in django_configs.items():
            config_type = type(value).__name__
            analysis["config_types"][config_type] = analysis["config_types"].get(config_type, 0) + 1
            if self._is_sensitive_config_key(key):
                analysis["sensitive_configs"].append(key)
            if isinstance(value, (dict, list)) and len(str(value)) > 100:
                analysis["complex_configs"].append(key)
        analysis_file = os.path.join(self.backup_dir, f"{self._current_migration.migration_id}_analysis.json")
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)

    def _create_config_schema(self) -> None:
        from .schema.schema import ConfigSchema

        schema = ConfigSchema()
        self._register_django_core_fields(schema)
        self._register_service_fields(schema)
        self._register_business_fields(schema)
        self.config_manager.set_schema(schema)

    def _register_django_core_fields(self, schema: Any) -> None:
        from .schema.field import ConfigField

        schema.register(
            ConfigField(
                name="django.secret_key",
                type=str,
                required=True,
                sensitive=True,
                description="Django 密钥",
                env_var="DJANGO_SECRET_KEY",
            )
        )
        schema.register(
            ConfigField(
                name="django.debug",
                type=bool,
                default=False,
                description="调试模式",
                env_var="DJANGO_DEBUG",
            )
        )
        schema.register(
            ConfigField(
                name="django.allowed_hosts",
                type=list,
                default=["localhost"],
                description="允许的主机列表",
                env_var="DJANGO_ALLOWED_HOSTS",
            )
        )
        schema.register(
            ConfigField(
                name="database.engine",
                type=str,
                default="django.db.backends.sqlite3",
                description="数据库引擎",
            )
        )
        schema.register(
            ConfigField(
                name="database.name",
                type=str,
                required=True,
                description="数据库名称",
                env_var="DB_NAME",
            )
        )

    def _register_service_fields(self, schema: Any) -> None:
        from .schema.field import ConfigField

        schema.register(
            ConfigField(
                name="services.moonshot.base_url",
                type=str,
                default="https://api.moonshot.cn/v1",
                description="Moonshot API 基础URL",
                env_var="MOONSHOT_BASE_URL",
            )
        )
        schema.register(
            ConfigField(
                name="services.moonshot.api_key",
                type=str,
                required=True,
                sensitive=True,
                description="Moonshot API 密钥",
                env_var="MOONSHOT_API_KEY",
            )
        )
        schema.register(
            ConfigField(
                name="services.ollama.model",
                type=str,
                default="qwen2.5:7b",
                description="Ollama 模型名称",
                env_var="OLLAMA_MODEL",
            )
        )
        schema.register(
            ConfigField(
                name="services.ollama.base_url",
                type=str,
                default="http://localhost:11434",
                description="Ollama 基础URL",
                env_var="OLLAMA_BASE_URL",
            )
        )

    def _register_business_fields(self, schema: Any) -> None:
        from .schema.field import ConfigField

        schema.register(
            ConfigField(
                name="chat_platforms.feishu.app_id",
                type=str,
                required=True,
                sensitive=True,
                description="飞书应用ID",
                env_var="FEISHU_APP_ID",
            )
        )
        schema.register(
            ConfigField(
                name="chat_platforms.feishu.app_secret",
                type=str,
                required=True,
                sensitive=True,
                description="飞书应用密钥",
                env_var="FEISHU_APP_SECRET",
            )
        )
        schema.register(
            ConfigField(
                name="chat_platforms.feishu.timeout",
                type=int,
                default=30,
                min_value=1,
                max_value=300,
                description="飞书API超时时间(秒)",
                env_var="FEISHU_TIMEOUT",
            )
        )
        schema.register(
            ConfigField(
                name="features.case_chat.default_platform",
                type=str,
                default="feishu",
                description="默认群聊平台",
            )
        )
        schema.register(
            ConfigField(
                name="features.case_chat.auto_create_on_push",
                type=bool,
                default=True,
                description="推送时自动创建群聊",
            )
        )

    def _migrate_core_configs(self) -> None:
        if self._current_migration is None:
            raise ConfigException("没有正在进行的迁移")
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
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
                old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                self.config_manager.set(config_key, value)
                self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
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
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    new_value = db_config.get(db_key, default)
                    self.config_manager.set(config_key, new_value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
                migrated_count += 1
        self._current_migration.migrated_configs += migrated_count

    def _migrate_service_configs(self) -> None:
        if self._current_migration is None:
            raise ConfigException("没有正在进行的迁移")
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
        simple_mappings = {
            "MOONSHOT_BASE_URL": "services.moonshot.base_url",
            "MOONSHOT_API_KEY": "services.moonshot.api_key",
        }
        for django_key, config_key in simple_mappings.items():
            if django_key in django_configs:
                old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                new_value = django_configs[django_key]
                self.config_manager.set(config_key, new_value)
                self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
                migrated_count += 1
        if "OLLAMA" in django_configs:
            ollama_config = django_configs["OLLAMA"]
            if isinstance(ollama_config, dict):
                for ollama_key, config_key in [
                    ("MODEL", "services.ollama.model"),
                    ("BASE_URL", "services.ollama.base_url"),
                ]:
                    if ollama_key in ollama_config:
                        old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                        new_value = ollama_config[ollama_key]
                        self.config_manager.set(config_key, new_value)
                        self._track_config_change(
                            self._current_migration.migration_id,
                            config_key,
                            old_value,
                            new_value,
                        )
                migrated_count += 1
        self._current_migration.migrated_configs += migrated_count

    def _migrate_business_configs(self) -> None:
        if self._current_migration is None:
            raise ConfigException("没有正在进行的迁移")
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
        business_keys = {
            "FEISHU": "chat_platforms.feishu",
            "CASE_CHAT": "features.case_chat",
            "COURT_SMS_PROCESSING": "features.court_sms",
        }
        for django_key, prefix in business_keys.items():
            if django_key not in django_configs:
                continue
            cfg = django_configs[django_key]
            if isinstance(cfg, dict):
                for key, value in cfg.items():
                    config_key = f"{prefix}.{key.lower()}"
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    self.config_manager.set(config_key, value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
        self._current_migration.migrated_configs += migrated_count

    def _validate_migrated_config(self) -> None:
        self.config_manager.load(force_reload=True)
        required_configs = ["django.secret_key", "django.debug", "django.allowed_hosts"]
        missing_configs = [k for k in required_configs if not self.config_manager.has(k)]
        if missing_configs:
            raise ConfigValidationError(missing_configs)

    def _create_compatibility_layer(self) -> None:
        pass  # 兼容层已在初始化时创建
