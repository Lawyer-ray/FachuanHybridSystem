from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

if TYPE_CHECKING:
    from apps.batch_printing.models import BatchPrintJob


@receiver(post_delete, sender="batch_printing.BatchPrintJob")
def delete_job_files(sender: type, instance: BatchPrintJob, **kwargs: object) -> None:
    """删除任务时清理关联文件目录。"""
    from apps.batch_printing.services.storage import BatchPrintStorage

    storage = BatchPrintStorage(instance.id)
    transaction.on_commit(storage.cleanup)
