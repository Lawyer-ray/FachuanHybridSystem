from __future__ import annotations

from django.apps import AppConfig


class WechatMpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.wechat_mp"
    verbose_name = "公众号发布"

    def ready(self) -> None:
        import apps.wechat_mp.signals
