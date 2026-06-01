"""Django app configuration."""

from django.apps import AppConfig


class RemindersConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.reminders"
    verbose_name = "重要日期提醒"
