"""Core 应用配置"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "核心系统"

    def ready(self) -> None:
        from . import admin
