from __future__ import annotations

from django.apps import AppConfig

class ContentOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content_ops"
    verbose_name = "内容运营"

    def ready(self) -> None:
        from . import signals
