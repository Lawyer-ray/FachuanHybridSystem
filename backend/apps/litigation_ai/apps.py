"""Django app configuration."""

from django.apps import AppConfig


class LitigationAIConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.litigation_ai"
    verbose_name: str = "AI 诉讼文书生成"
