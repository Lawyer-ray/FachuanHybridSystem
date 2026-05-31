from __future__ import annotations

from django.apps import AppConfig

class DocumentRecognitionConfig(AppConfig):
    """Document recognition app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.document_recognition"
    verbose_name: str = "文书智能识别"  # type: ignore[assignment]
