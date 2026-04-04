"""证据管理模块"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EvidenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evidence"
    verbose_name = _("证据管理")

    def ready(self) -> None:
        from . import signals
