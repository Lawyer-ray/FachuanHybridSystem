from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cases"
    verbose_name = _("案件管理")

    def ready(self) -> None:
        from . import signals  # noqa: F401 注册 post_delete 信号处理器
