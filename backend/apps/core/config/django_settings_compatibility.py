"""Module for django settings compatibility."""

import logging
from typing import Any

from django.conf import settings as django_settings

from .manager import ConfigManager

logger = logging.getLogger(__name__)


class DjangoSettingsCompatibilityLayer:
    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
        self._django_to_config_mapping = self._build_mapping()

    def _build_mapping(self) -> dict[str, str]:
        return {
            "SECRET_KEY": "django.secret_key",
            "DEBUG": "django.debug",
            "ALLOWED_HOSTS": "django.allowed_hosts",
            "DATABASES": "database",
            "LANGUAGE_CODE": "django.language_code",
            "TIME_ZONE": "django.time_zone",
            "USE_I18N": "django.use_i18n",
            "USE_TZ": "django.use_tz",
            "STATIC_URL": "django.static_url",
            "MEDIA_URL": "django.media_url",
            "MEDIA_ROOT": "django.media_root",
            "CORS_ALLOW_ALL_ORIGINS": "cors.allow_all_origins",
            "CORS_ALLOWED_ORIGINS": "cors.allowed_origins",
            "CORS_ALLOW_CREDENTIALS": "cors.allow_credentials",
            "CSRF_TRUSTED_ORIGINS": "cors.csrf_trusted_origins",
            "MOONSHOT_BASE_URL": "services.moonshot.base_url",
            "MOONSHOT_API_KEY": "services.moonshot.api_key",
            "OLLAMA": "services.ollama",
            "FEISHU": "chat_platforms.feishu",
            "DINGTALK": "chat_platforms.dingtalk",
            "WECHAT_WORK": "chat_platforms.wechat_work",
            "TELEGRAM": "chat_platforms.telegram",
            "SLACK": "chat_platforms.slack",
            "CASE_CHAT": "features.case_chat",
            "COURT_SMS_PROCESSING": "features.court_sms",
            "DOCUMENT_PROCESSING": "features.document_processing",
            "Q_CLUSTER": "performance.q_cluster",
            "RATE_LIMIT": "performance.rate_limit",
            "CACHES": "performance.cache",
            "SCRAPER_ENCRYPTION_KEY": "security.scraper_encryption_key",
            "PERM_OPEN_ACCESS": "security.perm_open_access",
        }

    def get_config_value(self, django_key: str, default: Any | None = None) -> Any:
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            try:
                return self.config_manager.get(config_key, default)
            except Exception as e:
                logger.debug(f"Failed to get config {config_key} from manager: {e}")

        return getattr(django_settings, django_key, default)

    def has_config(self, django_key: str) -> bool:
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            if self.config_manager.has(config_key):
                return True

        return hasattr(django_settings, django_key)

    def set_config_value(self, django_key: str, value: Any) -> None:
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            self.config_manager.set(config_key, value)
        else:
            setattr(django_settings, django_key, value)

    def get_all_django_configs(self) -> dict[str, Any]:
        configs: dict[str, Any] = {}
        for attr_name in dir(django_settings):
            if not attr_name.startswith("_") and attr_name.isupper():
                try:
                    configs[attr_name] = getattr(django_settings, attr_name)
                except Exception:
                    logger.exception("操作失败")

                    continue
        return configs
