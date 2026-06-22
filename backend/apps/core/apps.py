"""Core 应用配置"""

import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "核心系统"

    def ready(self) -> None:  # pragma: no cover
        # 恢复因 runserver auto-reload 中断的 OAuth device code 轮询
        try:
            from .cloud_storage.admin import resume_pending_device_code_polls

            resume_pending_device_code_polls()
        except Exception:
            # 数据库未就绪（如 migrate 阶段）时静默跳过
            logger.debug("跳过 device code 恢复（数据库可能未就绪）")

        # 注册文件清理定时任务
        try:
            from .tasking.cleanup_tasks import _register_schedules

            _register_schedules()
        except Exception:
            logger.debug("cleanup_tasks 调度注册跳过（未就绪）")

        # 注册 post_migrate 信号,首次 migrate 后自动加载种子数据
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._on_post_migrate, sender=self)

    def _on_post_migrate(self, sender, **kwargs):  # type: ignore[no-untyped-def]
        """数据库迁移完成后自动加载种子数据(仅表为空时)."""
        if "test" in sys.argv or "pytest" in sys.modules:
            return
        try:
            from .services.seed_data_loader import load_cause_seed_data, load_court_seed_data

            load_cause_seed_data()
            load_court_seed_data()
        except Exception as e:
            logger.warning("种子数据自动加载跳过: %s", e)
