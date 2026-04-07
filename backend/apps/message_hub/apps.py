"""Message Hub app config."""

from typing import Any

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MessageHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.message_hub"
    verbose_name = _("信息中转站")

    def ready(self) -> None:
        from django.db.models.signals import post_migrate

        from apps.message_hub import admin  # 触发 Admin 注册

        def _on_post_migrate(sender: Any, **kwargs: Any) -> None:
            from apps.message_hub import tasks  # 触发任务注册

        post_migrate.connect(_on_post_migrate, sender=self)
