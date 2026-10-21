"""Django app configuration."""

from django.apps import AppConfig


class AgentConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.agent"
    verbose_name = "Agent 运行时（pi）"
