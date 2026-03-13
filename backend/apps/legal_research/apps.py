from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LegalResearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.legal_research"
    verbose_name = _("案例检索")
