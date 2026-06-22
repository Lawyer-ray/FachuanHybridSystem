"""Message Hub app config — 纯 model app。

Admin / Services / API / Tasks 已迁移到 plugins/message_hub/。
"""

from django.apps import AppConfig


class MessageHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.message_hub"
    label = "message_hub"
    verbose_name = "信息中转站"

    def ready(self) -> None:  # pragma: no cover
        try:
            from plugins.message_hub.tasks import _register_schedule

            _register_schedule()
        except Exception:
            pass
