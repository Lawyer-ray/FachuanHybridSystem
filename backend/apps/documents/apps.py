"""Django app configuration."""

from __future__ import annotations

import logging
import sys
from typing import Any

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class DocumentsConfig(AppConfig):
    """法律文书生成系统应用配置"""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.documents"
    verbose_name = _("文书生成")

    def ready(self) -> None:
        """应用启动时的初始化"""
        from .services.code_placeholders.autodiscover import autodiscover_code_placeholders

        autodiscover_code_placeholders()

        # 注册信号处理器（包含缓存失效逻辑）
        from django.db.models.signals import post_migrate

        from . import signals

        post_migrate.connect(self._on_post_migrate, sender=self)

    def _on_post_migrate(self, sender: Any, **kwargs: Any) -> None:
        """
        数据库迁移完成后自动初始化默认文件夹模板

        这个方法在 migrate 命令执行完成后触发,确保:
        1. 数据库表已创建
        2. 不会在每次启动时重复执行(仅在 migrate 后)
        """
        if "test" in sys.argv or "pytest" in sys.modules:
            return
        try:
            from .models import FolderTemplate

            if FolderTemplate.objects.exists():
                return
            logger.info("首次迁移完成，暂无默认文件夹模板，请手动在后台创建。")
        except Exception as e:
            logger.warning("文件夹模板初始化检查跳过: %s", e)
