from __future__ import annotations

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """Finance app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.finance"
    verbose_name: str = "金融工具"

    def ready(self) -> None:
        """App ready hook."""
        pass
