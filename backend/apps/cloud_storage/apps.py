"""Django app config for the extracted cloud storage app (moved out of core)."""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CloudStorageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cloud_storage"
    label = "cloud_storage"
    verbose_name = "云存储"

    def ready(self) -> None:  # pragma: no cover
        # 恢复因 runserver auto-reload 中断的 OAuth device code 轮询
        # （原逻辑位于 apps/core/apps.py，随拆分迁入本 app）
        import sys

        # migrate 前表尚不存在 / 测试环境跳过，与原 core/apps.py 行为一致
        if "migrate" in sys.argv or "makemigrations" in sys.argv or "test" in sys.argv:
            return
        # ASGI（uvicorn）下 AppConfig.ready 运行在事件循环内，同步 ORM 会抛
        # SynchronousOnlyOperation——原 core 版以宽 except 静默跳过该场景，此处保持一致。
        try:
            from .admin import resume_pending_device_code_polls

            with allow_startup_db():
                resume_pending_device_code_polls()
        except Exception:
            # 数据库未就绪（如 migrate 阶段）或运行在异步上下文时静默跳过
            logger.debug("跳过 device code 恢复（数据库可能未就绪或处于异步上下文）")


def allow_startup_db():
    """Allow DB access during AppConfig.ready() startup.

    保留 core/apps.py 原实现语义：项目自定义的启动期数据库访问放行器。
    这里延迟导入以避免在 core 完全加载前引发循环导入。
    """
    from apps.core.utils.startup_db import allow_startup_db as _impl

    return _impl()
