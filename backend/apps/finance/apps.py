from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinanceConfig(AppConfig):
    """Finance app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.finance"
    verbose_name: str = _("金融工具")  # type: ignore[assignment]

    def ready(self) -> None:
        """App ready hook."""
        pass
