from __future__ import annotations

from django.apps import AppConfig


class SocialAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.social_auth"
    verbose_name = "社交登录"

    def ready(self) -> None:
        from . import providers
