"""Core 应用配置"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "核心系统"

    def ready(self) -> None:

        # 恢复因 runserver auto-reload 中断的 OAuth device code 轮询
        try:
            from .cloud_storage.admin import resume_pending_device_code_polls

            resume_pending_device_code_polls()
        except Exception:
            # 数据库未就绪（如 migrate 阶段）时静默跳过
            logger.debug("跳过 device code 恢复（数据库可能未就绪）")
