from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ExpressQueryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.express_query"
    verbose_name = _("快递查询")

    def ready(self) -> None:
        """应用启动时连接信号"""
        import apps.express_query.signals
