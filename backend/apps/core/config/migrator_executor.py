"""
配置迁移执行器

负责执行具体的配置迁移操作
"""

from __future__ import annotations

import logging
from typing import Any, cast

from django.conf import settings as django_settings

from .manager import ConfigManager
from .migrator_models import MigrationStep

logger = logging.getLogger(__name__)


class MigrationExecutor:
    """迁移执行器"""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        初始化执行器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

    def migrate_core_configs(self, step: MigrationStep) -> None:
        """
        迁移核心配置

        Args:
            step: 迁移步骤
        """
        step.start()
        try:
            # Django 核心配置
            core_attrs = [
                ("SECRET_KEY", "django.secret_key"),
                ("DEBUG", "django.debug"),
                ("ALLOWED_HOSTS", "django.allowed_hosts"),
                ("LANGUAGE_CODE", "django.language_code"),
                ("TIME_ZONE", "django.time_zone"),
                ("USE_I18N", "django.use_i18n"),
                ("USE_TZ", "django.use_tz"),
                ("STATIC_URL", "django.static_url"),
                ("MEDIA_URL", "django.media_url"),
                ("MEDIA_ROOT", "django.media_root"),
            ]
            _s: Any = cast(Any, django_settings)
            for attr, key in core_attrs:
                if hasattr(django_settings, attr):
                    self.config_manager.set(key, getattr(_s, attr))

            step.complete()
            logger.info("核心配置迁移完成")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"核心配置迁移失败: {e}")
            raise

    def migrate_service_configs(self, step: MigrationStep) -> None:
        """
        迁移服务配置

        Args:
            step: 迁移步骤
        """
        step.start()
        try:
            _s: Any = cast(Any, django_settings)
            # CORS 配置
            if hasattr(django_settings, "CORS_ALLOW_ALL_ORIGINS"):
                self.config_manager.set("cors.allow_all_origins", _s.CORS_ALLOW_ALL_ORIGINS)

            if hasattr(django_settings, "CORS_ALLOWED_ORIGINS"):
                self.config_manager.set("cors.allowed_origins", _s.CORS_ALLOWED_ORIGINS)

            if hasattr(django_settings, "CORS_ALLOW_CREDENTIALS"):
                self.config_manager.set("cors.allow_credentials", _s.CORS_ALLOW_CREDENTIALS)

            if hasattr(django_settings, "CSRF_TRUSTED_ORIGINS"):
                self.config_manager.set("cors.csrf_trusted_origins", _s.CSRF_TRUSTED_ORIGINS)

            # 第三方服务配置
            if hasattr(django_settings, "MOONSHOT_BASE_URL"):
                self.config_manager.set("services.moonshot.base_url", _s.MOONSHOT_BASE_URL)

            if hasattr(django_settings, "MOONSHOT_API_KEY"):
                self.config_manager.set("services.moonshot.api_key", _s.MOONSHOT_API_KEY)

            if hasattr(django_settings, "OLLAMA"):
                self.config_manager.set("services.ollama", _s.OLLAMA)

            step.complete()
            logger.info("服务配置迁移完成")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"服务配置迁移失败: {e}")
            raise

    def migrate_business_configs(self, step: MigrationStep) -> None:
        """
        迁移业务配置

        Args:
            step: 迁移步骤
        """
        step.start()
        try:
            # 群聊平台 + 业务功能 + 性能 + 安全配置
            simple_attrs = [
                ("FEISHU", "chat_platforms.feishu"),
                ("DINGTALK", "chat_platforms.dingtalk"),
                ("WECHAT_WORK", "chat_platforms.wechat_work"),
                ("TELEGRAM", "chat_platforms.telegram"),
                ("SLACK", "chat_platforms.slack"),
                ("CASE_CHAT", "features.case_chat"),
                ("COURT_SMS_PROCESSING", "features.court_sms"),
                ("DOCUMENT_PROCESSING", "features.document_processing"),
                ("Q_CLUSTER", "performance.q_cluster"),
                ("RATE_LIMIT", "performance.rate_limit"),
                ("CACHES", "performance.cache"),
                ("SCRAPER_ENCRYPTION_KEY", "security.scraper_encryption_key"),
                ("PERM_OPEN_ACCESS", "security.perm_open_access"),
            ]
            _s: Any = cast(Any, django_settings)
            for attr, key in simple_attrs:
                if hasattr(django_settings, attr):
                    self.config_manager.set(key, getattr(_s, attr))

            step.complete()
            logger.info("业务配置迁移完成")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"业务配置迁移失败: {e}")
            raise
