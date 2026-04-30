from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LegalSolutionConfig(AppConfig):
    name = "apps.legal_solution"
    verbose_name = _("法律服务方案")

    def ready(self) -> None:
        from . import signals
