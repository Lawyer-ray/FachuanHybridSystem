from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FeeNoticeConfig(AppConfig):
    """Fee notice app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.fee_notice"
    verbose_name: str = _("交费通知书识别")
