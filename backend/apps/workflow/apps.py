"""工作流引擎 App 配置"""

from __future__ import annotations

from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workflow"
    verbose_name = "工作流引擎"
