"""证据管理模块"""

from django.apps import AppConfig


class EvidenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evidence"
    verbose_name = "证据管理"

    def ready(self) -> None:  # pragma: no cover
        from . import signals
