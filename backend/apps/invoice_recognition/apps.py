from __future__ import annotations

from django.apps import AppConfig

class InvoiceRecognitionConfig(AppConfig):
    """Invoice recognition app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.invoice_recognition"
    verbose_name: str = "发票识别"  # type: ignore[assignment]
