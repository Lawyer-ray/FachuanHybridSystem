from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PreservationDateConfig(AppConfig):
    """Preservation date app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.preservation_date"
    verbose_name: str = _("财产保全日期识别")  # type: ignore[assignment]
