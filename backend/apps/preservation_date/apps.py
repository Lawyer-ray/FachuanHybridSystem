from __future__ import annotations

from django.apps import AppConfig


class PreservationDateConfig(AppConfig):
    """Preservation date app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.preservation_date"
    verbose_name: str = "财产保全日期识别"
