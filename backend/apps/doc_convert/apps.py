"""doc_convert app 配置。"""

from __future__ import annotations

from django.apps import AppConfig


class DocConvertConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_convert"
    verbose_name = "要素式转换"

    def ready(self) -> None:  # pragma: no cover
        import apps.doc_convert.signals
