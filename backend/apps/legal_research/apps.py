from __future__ import annotations

from django.apps import AppConfig

class LegalResearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.legal_research"
    verbose_name = "案例检索"

    def ready(self) -> None:
        from . import signals
