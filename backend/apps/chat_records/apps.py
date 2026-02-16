"""Django app configuration."""

from __future__ import annotations

from typing import Any

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatRecordsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.chat_records"
    verbose_name = _("梳理聊天记录")

    def ready(self) -> Any:
        pass
