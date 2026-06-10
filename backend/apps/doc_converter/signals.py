from __future__ import annotations

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DocConverterItem, DocConverterJob

logger = logging.getLogger("apps.doc_converter")


@receiver(post_delete, sender=DocConverterJob)
def _cleanup_job_files(sender: type, instance: DocConverterJob, **kwargs: object) -> None:  # pragma: no cover
    from apps.doc_converter.services.storage import DocConverterStorage

    if instance.output_zip:
        try:
            instance.output_zip.delete(save=False)
        except Exception:
            logger.exception("清理 job output_zip 失败: %s", instance.id)

    storage = DocConverterStorage(instance.id)
    storage.cleanup()


@receiver(post_delete, sender=DocConverterItem)
def _cleanup_item_files(sender: type, instance: DocConverterItem, **kwargs: object) -> None:  # pragma: no cover
    for field in (instance.source_file, instance.converted_file):
        if field:
            try:
                field.delete(save=False)
            except Exception:
                logger.exception("清理 item 文件失败: %s", instance.id)
