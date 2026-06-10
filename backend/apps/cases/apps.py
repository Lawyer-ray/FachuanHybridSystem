from __future__ import annotations

from django.apps import AppConfig


class CasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cases"
    verbose_name = "案件管理"

    def ready(self) -> None:  # pragma: no cover
        from . import signals
