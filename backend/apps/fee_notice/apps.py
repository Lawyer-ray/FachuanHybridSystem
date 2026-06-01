from __future__ import annotations

from django.apps import AppConfig


class FeeNoticeConfig(AppConfig):
    """Fee notice app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.fee_notice"
    verbose_name: str = "交费通知书识别"
