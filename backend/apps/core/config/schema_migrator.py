"""Module for schema migrator."""

from __future__ import annotations

"""
配置模式迁移器

负责分析 Django settings 并创建统一配置模式(Schema),
包括 Django 核心配置、服务配置和业务配置的字段注册.
"""


import json
import logging
import os
from typing import Any

from django.conf import settings as django_settings

from .manager import ConfigManager
from .migrator_models import MigrationLog
from .schema.field import ConfigField
from .schema.schema import ConfigSchema

logger = logging.getLogger(__name__)


class DjangoSettingsCompatibilityLayer:
    """Django Settings 兼容层"""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        初始化兼容层

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self._django_to_config_mapping = self._build_mapping()

    def _build_mapping(self) -> dict[str, str]:
        """
        构建 Django settings 到统一配置的映射

        Returns:
            Dict[str, str]: 映射字典
        """
        return {
            # Django 核心配置
            "SECRET_KEY": "django.secret_key",
            "DEBUG": "django.debug",
            "ALLOWED_HOSTS": "django.allowed_hosts",
            # 数据库配置
            "DATABASES": "database",
            # 国际化配置
            "LANGUAGE_CODE": "django.language_code",
            "TIME_ZONE": "django.time_zone",
            "USE_I18N": "django.use_i18n",
            "USE_TZ": "django.use_tz",
            # 静态文件配置
            "STATIC_URL": "django.static_url",
            "MEDIA_URL": "django.media_url",
            "MEDIA_ROOT": "django.media_root",
            # CORS 配置
            "CORS_ALLOW_ALL_ORIGINS": "cors.allow_all_origins",
            "CORS_ALLOWED_ORIGINS": "cors.allowed_origins",
            "CORS_ALLOW_CREDENTIALS": "cors.allow_credentials",
            "CSRF_TRUSTED_ORIGINS": "cors.csrf_trusted_origins",
            # 第三方服务配置
            "MOONSHOT_BASE_URL": "services.moonshot.base_url",
            "MOONSHOT_API_KEY": "services.moonshot.api_key",
            "OLLAMA": "services.ollama",
            # 群聊平台配置
            "FEISHU": "chat_platforms.feishu",
            "DINGTALK": "chat_platforms.dingtalk",
            "WECHAT_WORK": "chat_platforms.wechat_work",
            "TELEGRAM": "chat_platforms.telegram",
            "SLACK": "chat_platforms.slack",
            # 业务功能配置
            "CASE_CHAT": "features.case_chat",
            "COURT_SMS_PROCESSING": "features.court_sms",
            "DOCUMENT_PROCESSING": "features.document_processing",
            # 性能配置
            "Q_CLUSTER": "performance.q_cluster",
            "RATE_LIMIT": "performance.rate_limit",
            "CACHES": "performance.cache",
            # 其他配置
            "SCRAPER_ENCRYPTION_KEY": "security.scraper_encryption_key",
            "PERM_OPEN_ACCESS": "security.perm_open_access",
        }

    def get_config_value(self, django_key: str, default: Any | None = None) -> Any:
        """
        获取配置值(兼容 Django settings 访问方式)

        Args:
            django_key: Django 配置键
            default: 默认值

        Returns:
            配置值
        """
        # 首先尝试从统一配置获取
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            try:
                return self.config_manager.get(config_key, default)
            except Exception:
                logger.exception("操作失败")

                pass

        # 回退到 Django settings
        return getattr(django_settings, django_key, default)

    def has_config(self, django_key: str) -> bool:
        """
        检查配置是否存在

        Args:
            django_key: Django 配置键

        Returns:
            bool: 是否存在
        """
        # 检查统一配置
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            if self.config_manager.has(config_key):
                return True

        # 检查 Django settings
        return hasattr(django_settings, django_key)

    def set_config_value(self, django_key: str, value: Any) -> None:
        """
        设置配置值

        Args:
            django_key: Django 配置键
            value: 配置值
        """
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            self.config_manager.set(config_key, value)
        else:
            # 设置到 Django settings(如果可能)
            setattr(django_settings, django_key, value)

    def get_all_django_configs(self) -> dict[str, Any]:
        """
        获取所有 Django 配置

        Returns:
            Dict[str, Any]: Django 配置字典
        """
        configs = {}

        # 获取所有 Django settings 属性
        for attr_name in dir(django_settings):
            if not attr_name.startswith("_") and attr_name.isupper():
                try:
                    configs[attr_name] = getattr(django_settings, attr_name)
                except Exception:
                    logger.exception("操作失败")

                    # 忽略无法获取的属性
                    continue

        return configs


def is_sensitive_config_key(key: str) -> bool:
    """
    检查配置键是否为敏感配置

    Args:
        key: 配置键

    Returns:
        bool: 是否为敏感配置
    """
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

    key_upper = key.upper()
    return any(keyword in key_upper for keyword in sensitive_keywords)


def analyze_django_settings(
    compatibility_layer: DjangoSettingsCompatibilityLayer,
    current_migration: MigrationLog,
    backup_dir: str,
) -> None:
    """分析 Django Settings"""

    django_configs = compatibility_layer.get_all_django_configs()
    current_migration.total_configs = len(django_configs)

    # 分析配置类型和结构
    analysis: dict[str, Any] = {
        "total_configs": len(django_configs),
        "config_types": {},
        "sensitive_configs": [],
        "complex_configs": [],
    }

    for key, value in django_configs.items():
        # 分析配置类型
        config_type = type(value).__name__
        analysis["config_types"][config_type] = analysis["config_types"].get(config_type, 0) + 1

        # 识别敏感配置
        if is_sensitive_config_key(key):
            analysis["sensitive_configs"].append(key)

        # 识别复杂配置
        if isinstance(value, (dict, list)) and len(str(value)) > 100:
            analysis["complex_configs"].append(key)

    # 保存分析结果
    analysis_file = os.path.join(backup_dir, f"{current_migration.migration_id}_analysis.json")

    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)


def create_config_schema(config_manager: ConfigManager) -> None:
    """创建配置模式"""
    schema = ConfigSchema()  # type: ignore[no-untyped-call]

    # 注册 Django 核心配置字段
    _register_django_core_fields(schema)

    # 注册服务配置字段
    _register_service_fields(schema)

    # 注册业务配置字段
    _register_business_fields(schema)

    # 设置到配置管理器
    config_manager.set_schema(schema)


def _register_django_core_fields(schema: ConfigSchema) -> None:
    """注册 Django 核心配置字段"""
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
        ConfigField(name="django.debug", type=bool, default=False, description="调试模式", env_var="DJANGO_DEBUG")
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

    # 数据库配置
    schema.register(
        ConfigField(name="database.engine", type=str, default="django.db.backends.sqlite3", description="数据库引擎")
    )

    schema.register(
        ConfigField(name="database.name", type=str, required=True, description="数据库名称", env_var="DB_NAME")
    )


def _register_service_fields(schema: ConfigSchema) -> None:
    """注册服务配置字段"""
    # Moonshot AI 配置
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

    # Ollama 配置
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


def _register_business_fields(schema: ConfigSchema) -> None:
    """注册业务配置字段"""
    # 飞书配置
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

    # 案件群聊配置
    schema.register(
        ConfigField(name="features.case_chat.default_platform", type=str, default="feishu", description="默认群聊平台")
    )

    schema.register(
        ConfigField(
            name="features.case_chat.auto_create_on_push", type=bool, default=True, description="推送时自动创建群聊"
        )
    )
