"""Django app configuration."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RemindersConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.reminders"
    verbose_name = _("重要日期提醒")
