"""Django app configuration."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LitigationAIConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.litigation_ai"
    verbose_name = _("AI 诉讼文书生成")
