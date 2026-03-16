from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocumentRecognitionConfig(AppConfig):
    """Document recognition app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.document_recognition"
    verbose_name: str = _("文书智能识别")
