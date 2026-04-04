"""evidence app 信号处理器 - 删除证据时自动清理附件物理文件"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _delete_file(field_file: Any) -> None:
    """删除 FileField 对应的物理文件"""
    if field_file:
        try:
            field_file.delete(save=False)
            logger.info("已清理证据附件物理文件", extra={"file_path": str(field_file)})
        except Exception:
            logger.exception("清理证据附件失败")


@receiver(post_delete, dispatch_uid="cleanup_evidence_item_file")
def cleanup_evidence_item_file(sender: type, **kwargs: Any) -> None:
    from .models import EvidenceItem  # 防止循环导入

    if sender is EvidenceItem:
        instance = kwargs["instance"]
        _delete_file(instance.file)


@receiver(post_delete, dispatch_uid="cleanup_evidence_list_merged_pdf")
def cleanup_evidence_list_merged_pdf(sender: type, **kwargs: Any) -> None:
    from .models import EvidenceList  # 防止循环导入

    if sender is EvidenceList:
        instance = kwargs["instance"]
        _delete_file(instance.merged_pdf)
