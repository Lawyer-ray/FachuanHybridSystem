from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

if TYPE_CHECKING:
    from apps.pdf_splitting.models import PdfSplitJob


@receiver(post_delete, sender="pdf_splitting.PdfSplitJob")
def delete_job_files(sender: type, instance: PdfSplitJob, **kwargs: object) -> None:
    """删除任务时清理关联的文件目录"""
    from apps.pdf_splitting.services.storage import PdfSplitStorage

    storage = PdfSplitStorage(instance.id)
    transaction.on_commit(storage.cleanup)
