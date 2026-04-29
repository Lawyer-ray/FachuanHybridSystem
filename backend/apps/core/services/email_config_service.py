"""
邮件配置服务

从 SystemConfig 读取邮件服务器配置。
"""

from typing import Any

from django.core.cache import cache

from apps.core.services.system_config_service import SystemConfigService

_CACHE_KEY = "email_config"
_CACHE_TTL = 300  # 5 分钟


class EmailConfigService:
    """邮件配置服务"""

    _config_service: SystemConfigService | None = None

    @classmethod
    def _get_config_service(cls) -> SystemConfigService:
        if cls._config_service is None:
            cls._config_service = SystemConfigService()
        return cls._config_service

    @classmethod
    def get_config(cls) -> dict[str, Any]:
        """
        获取邮件配置

        Returns:
            包含邮件配置的字典
        """
        cached: dict[str, Any] | None = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached

        service = cls._get_config_service()

        config = {
            "EMAIL_HOST": service.get_value("EMAIL_HOST", ""),
            "EMAIL_PORT": int(service.get_value("EMAIL_PORT", "465")),
            "EMAIL_USE_SSL": service.get_value("EMAIL_USE_SSL", "true").lower() == "true",
            "EMAIL_USE_TLS": service.get_value("EMAIL_USE_TLS", "false").lower() == "true",
            "EMAIL_HOST_USER": service.get_value("EMAIL_HOST_USER", ""),
            "EMAIL_HOST_PASSWORD": service.get_value("EMAIL_HOST_PASSWORD", ""),
            "EMAIL_FROM_NAME": service.get_value("EMAIL_FROM_NAME", "法穿AI系统"),
            "EMAIL_SUBJECT_PREFIX": service.get_value("EMAIL_SUBJECT_PREFIX", "[法穿AI]"),
        }

        cache.set(_CACHE_KEY, config, _CACHE_TTL)
        return config

    @classmethod
    def is_configured(cls) -> bool:
        """
        检查邮件是否已配置

        Returns:
            是否已配置 SMTP 服务器和发件人邮箱
        """
        config = cls.get_config()
        return bool(config.get("EMAIL_HOST") and config.get("EMAIL_HOST_USER"))

    @classmethod
    def clear_cache(cls) -> None:
        """清除邮件配置缓存"""
        cache.delete(_CACHE_KEY)
