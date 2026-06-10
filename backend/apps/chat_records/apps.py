"""Django app configuration."""

from __future__ import annotations

from django.apps import AppConfig


class ChatRecordsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.chat_records"
    verbose_name = "梳理聊天记录"

    def ready(self) -> None:  # pragma: no cover
        from . import signals  # 注册 post_delete 和 pre_save 信号处理器
