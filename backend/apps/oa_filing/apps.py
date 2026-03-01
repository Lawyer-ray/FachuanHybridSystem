from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OaFilingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.oa_filing"
    verbose_name = _("OA立案")
