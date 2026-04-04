"""
Cases 模块信号处理器

处理案件相关模型删除时的物理文件清理（日志附件、裁判文书文件等）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_delete, sender="cases.CaseLogAttachment")
def _cleanup_log_attachment_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 CaseLogAttachment 时清理物理文件。"""
    if instance.file:
        try:
            instance.file.delete(save=False)
            logger.info(
                "已清理日志附件物理文件",
                extra={"attachment_id": instance.pk, "file_path": str(instance.file)},
            )
        except Exception:
            logger.exception(
                "清理日志附件物理文件失败",
                extra={"attachment_id": instance.pk},
            )


@receiver(post_delete, sender="cases.CaseNumber")
def _cleanup_case_number_document_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 CaseNumber 时清理裁判文书物理文件。"""
    if instance.document_file:
        try:
            instance.document_file.delete(save=False)
            logger.info(
                "已清理裁判文书物理文件",
                extra={"case_number_id": instance.pk, "file_path": str(instance.document_file)},
            )
        except Exception:
            logger.exception(
                "清理裁判文书物理文件失败",
                extra={"case_number_id": instance.pk},
            )
