"""法律服务方案模块信号处理

处理模型删除事件，自动触发文件清理。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.legal_solution")


@receiver(post_delete, sender="legal_solution.SolutionTask", dispatch_uid="cleanup_solution_task_pdf")
def _cleanup_solution_task_pdf(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 SolutionTask 时清理 PDF 物理文件。"""
    if instance.pdf_file:
        try:
            instance.pdf_file.delete(save=False)
            logger.info(
                "已清理法律服务方案PDF文件",
                extra={"task_id": instance.pk, "file_path": str(instance.pdf_file)},
            )
        except Exception:
            logger.exception(
                "清理法律服务方案PDF文件失败",
                extra={"task_id": instance.pk},
            )
