from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WechatMpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.wechat_mp"
    verbose_name = _("公众号发布")

    def ready(self) -> None:
        import apps.wechat_mp.signals
