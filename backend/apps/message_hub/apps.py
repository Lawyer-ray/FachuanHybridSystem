"""Message Hub app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
from typing import Any


class MessageHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.message_hub"
    verbose_name = _("信息中转站")

    def ready(self) -> None:
        from apps.message_hub import admin  # noqa: F401  触发 Admin 注册

        from django.db.models.signals import post_migrate

        def _on_post_migrate(sender: Any, **kwargs: Any) -> None:
            from apps.message_hub import tasks  # noqa: F401

        post_migrate.connect(_on_post_migrate, sender=self)
