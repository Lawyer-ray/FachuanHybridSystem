"""Django app configuration."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OnboardingConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.onboarding"
    verbose_name = _("立案引导")
