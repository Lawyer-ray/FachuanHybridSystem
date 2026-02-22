"""Core 应用配置"""

import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = _("核心系统")

    def ready(self) -> None:
        from . import admin  # noqa: F401 — 触发 admin 注册
