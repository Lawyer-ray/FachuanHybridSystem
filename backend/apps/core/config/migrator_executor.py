"""
配置迁移执行器

负责执行具体的配置迁移操作
"""

from __future__ import annotations

import logging

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
            if hasattr(django_settings, "SECRET_KEY"):
                self.config_manager.set("django.secret_key", django_settings.SECRET_KEY)

            if hasattr(django_settings, "DEBUG"):
                self.config_manager.set("django.debug", django_settings.DEBUG)

            if hasattr(django_settings, "ALLOWED_HOSTS"):
                self.config_manager.set("django.allowed_hosts", django_settings.ALLOWED_HOSTS)

            # 国际化配置
            if hasattr(django_settings, "LANGUAGE_CODE"):
                self.config_manager.set("django.language_code", django_settings.LANGUAGE_CODE)

            if hasattr(django_settings, "TIME_ZONE"):
                self.config_manager.set("django.time_zone", django_settings.TIME_ZONE)

            if hasattr(django_settings, "USE_I18N"):
                self.config_manager.set("django.use_i18n", django_settings.USE_I18N)

            if hasattr(django_settings, "USE_TZ"):
                self.config_manager.set("django.use_tz", django_settings.USE_TZ)

            # 静态文件配置
            if hasattr(django_settings, "STATIC_URL"):
                self.config_manager.set("django.static_url", django_settings.STATIC_URL)

            if hasattr(django_settings, "MEDIA_URL"):
                self.config_manager.set("django.media_url", django_settings.MEDIA_URL)

            if hasattr(django_settings, "MEDIA_ROOT"):
                self.config_manager.set("django.media_root", django_settings.MEDIA_ROOT)

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
            # CORS 配置
            if hasattr(django_settings, "CORS_ALLOW_ALL_ORIGINS"):
                self.config_manager.set("cors.allow_all_origins", django_settings.CORS_ALLOW_ALL_ORIGINS)

            if hasattr(django_settings, "CORS_ALLOWED_ORIGINS"):
                self.config_manager.set("cors.allowed_origins", django_settings.CORS_ALLOWED_ORIGINS)

            if hasattr(django_settings, "CORS_ALLOW_CREDENTIALS"):
                self.config_manager.set("cors.allow_credentials", django_settings.CORS_ALLOW_CREDENTIALS)

            if hasattr(django_settings, "CSRF_TRUSTED_ORIGINS"):
                self.config_manager.set("cors.csrf_trusted_origins", django_settings.CSRF_TRUSTED_ORIGINS)

            # 第三方服务配置
            if hasattr(django_settings, "MOONSHOT_BASE_URL"):
                self.config_manager.set("services.moonshot.base_url", django_settings.MOONSHOT_BASE_URL)

            if hasattr(django_settings, "MOONSHOT_API_KEY"):
                self.config_manager.set("services.moonshot.api_key", django_settings.MOONSHOT_API_KEY)

            if hasattr(django_settings, "OLLAMA"):
                self.config_manager.set("services.ollama", django_settings.OLLAMA)

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
            # 群聊平台配置
            if hasattr(django_settings, "FEISHU"):
                self.config_manager.set("chat_platforms.feishu", django_settings.FEISHU)

            if hasattr(django_settings, "DINGTALK"):
                self.config_manager.set("chat_platforms.dingtalk", django_settings.DINGTALK)

            if hasattr(django_settings, "WECHAT_WORK"):
                self.config_manager.set("chat_platforms.wechat_work", django_settings.WECHAT_WORK)

            if hasattr(django_settings, "TELEGRAM"):
                self.config_manager.set("chat_platforms.telegram", django_settings.TELEGRAM)

            if hasattr(django_settings, "SLACK"):
                self.config_manager.set("chat_platforms.slack", django_settings.SLACK)

            # 业务功能配置
            if hasattr(django_settings, "CASE_CHAT"):
                self.config_manager.set("features.case_chat", django_settings.CASE_CHAT)

            if hasattr(django_settings, "COURT_SMS_PROCESSING"):
                self.config_manager.set("features.court_sms", django_settings.COURT_SMS_PROCESSING)

            if hasattr(django_settings, "DOCUMENT_PROCESSING"):
                self.config_manager.set("features.document_processing", django_settings.DOCUMENT_PROCESSING)

            # 性能配置
            if hasattr(django_settings, "Q_CLUSTER"):
                self.config_manager.set("performance.q_cluster", django_settings.Q_CLUSTER)

            if hasattr(django_settings, "RATE_LIMIT"):
                self.config_manager.set("performance.rate_limit", django_settings.RATE_LIMIT)

            if hasattr(django_settings, "CACHES"):
                self.config_manager.set("performance.cache", django_settings.CACHES)

            # 安全配置
            if hasattr(django_settings, "SCRAPER_ENCRYPTION_KEY"):
                self.config_manager.set("security.scraper_encryption_key", django_settings.SCRAPER_ENCRYPTION_KEY)

            if hasattr(django_settings, "PERM_OPEN_ACCESS"):
                self.config_manager.set("security.perm_open_access", django_settings.PERM_OPEN_ACCESS)

            step.complete()
            logger.info("业务配置迁移完成")
        except Exception as e:
            step.fail(str(e))
            logger.error(f"业务配置迁移失败: {e}")
            raise
