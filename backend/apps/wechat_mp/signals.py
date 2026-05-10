"""公众号发布模块信号处理

处理模型删除事件，自动触发文件清理。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.wechat_mp")


@receiver(post_delete, sender="wechat_mp.PublishTask", dispatch_uid="cleanup_publishtask_cover_image")
def _cleanup_publishtask_cover_image(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 PublishTask 时清理封面图物理文件。"""
    if instance.cover_image:
        try:
            instance.cover_image.delete(save=False)
            logger.info(
                "已清理公众号封面图",
                extra={"task_id": instance.pk, "file_path": str(instance.cover_image)},
            )
        except Exception:
            logger.exception(
                "清理公众号封面图失败",
                extra={"task_id": instance.pk},
            )
