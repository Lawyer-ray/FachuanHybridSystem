"""组织管理模块信号处理

处理模型删除事件，自动触发文件清理。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.organization")


@receiver(post_delete, sender="organization.Lawyer", dispatch_uid="cleanup_lawyer_license_pdf")
def _cleanup_lawyer_license_pdf(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 Lawyer 时清理执业证 PDF 物理文件。"""
    if instance.license_pdf:
        try:
            instance.license_pdf.delete(save=False)
            logger.info(
                "已清理律师执业证文件",
                extra={"lawyer_id": instance.pk, "file_path": str(instance.license_pdf)},
            )
        except Exception:
            logger.exception(
                "清理律师执业证文件失败",
                extra={"lawyer_id": instance.pk},
            )
