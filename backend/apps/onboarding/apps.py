"""Django app configuration."""

from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.onboarding"
    verbose_name: str = "立案引导"
