from __future__ import annotations

from django.apps import AppConfig


class ExpressQueryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.express_query"
    verbose_name = "快递查询"

    def ready(self) -> None:  # pragma: no cover
        """应用启动时连接信号"""
        import apps.express_query.signals
