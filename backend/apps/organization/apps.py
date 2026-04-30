from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrganizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organization"
    verbose_name = _("组织管理")

    def ready(self) -> None:
        from . import signals
