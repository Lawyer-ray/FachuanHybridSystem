from __future__ import annotations

from django.apps import AppConfig

class OrganizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organization"
    verbose_name = "组织管理"

    def ready(self) -> None:
        from . import signals
