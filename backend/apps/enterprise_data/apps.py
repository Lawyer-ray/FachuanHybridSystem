from __future__ import annotations

from django.apps import AppConfig


class EnterpriseDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.enterprise_data"
    verbose_name = "企业数据查询"
