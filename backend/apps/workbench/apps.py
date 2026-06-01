"""工作台 App 配置"""

from __future__ import annotations

from django.apps import AppConfig


class WorkbenchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workbench"
    verbose_name = "工作台"
