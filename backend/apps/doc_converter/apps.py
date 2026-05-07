from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocConverterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_converter"
    verbose_name = _("DOC 转 DOCX")

    def ready(self) -> None:
        import apps.doc_converter.signals
