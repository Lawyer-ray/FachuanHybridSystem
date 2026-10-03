"""Message Hub app config。

收件箱通用能力（Admin / Services / API / Tasks）位于本 app；
「一张网收件箱 / 庭审日程」适配器由 plugins/message_hub/services/court/ 提供。
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MessageHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.message_hub"
    label = "message_hub"
    verbose_name = "信息中转站"

    def ready(self) -> None:  # pragma: no cover
        try:
            from apps.core.utils.startup_db import allow_startup_db
            from apps.message_hub.tasks import _register_schedule

            with allow_startup_db():
                _register_schedule()
        except Exception:
            logger.warning("注册 message_hub 定时任务调度失败（已忽略）", exc_info=True)
