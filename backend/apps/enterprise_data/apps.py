from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EnterpriseDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.enterprise_data"
    verbose_name = _("企业数据查询")
