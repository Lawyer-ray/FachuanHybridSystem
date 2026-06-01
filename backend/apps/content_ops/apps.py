from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content_ops"
    verbose_name = _("内容运营")

    def ready(self) -> None:
        from . import signals
