from __future__ import annotations

from django.apps import AppConfig


class DocConverterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_converter"
    verbose_name = "DOC 转 DOCX"

    def ready(self) -> None:
        import apps.doc_converter.signals
