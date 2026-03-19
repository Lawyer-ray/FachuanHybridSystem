from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InvoiceRecognitionConfig(AppConfig):
    """Invoice recognition app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.invoice_recognition"
    verbose_name: str = _("发票识别")
