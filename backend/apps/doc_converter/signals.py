from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DocConverterItem, DocConverterJob

logger = logging.getLogger("apps.doc_converter")


@receiver(post_delete, sender=DocConverterJob)
def _cleanup_job_files(sender: type, instance: DocConverterJob, **kwargs: object) -> None:  # pragma: no cover
    from apps.doc_converter.services.storage import DocConverterStorage

    zip_file = instance.output_zip
    storage = DocConverterStorage(instance.id)

    def _do_cleanup() -> None:
        if zip_file:
            try:
                zip_file.delete(save=False)
            except Exception:
                logger.exception("清理 job output_zip 失败: %s", instance.id)
        storage.cleanup()

    transaction.on_commit(_do_cleanup)


@receiver(post_delete, sender=DocConverterItem)
def _cleanup_item_files(sender: type, instance: DocConverterItem, **kwargs: object) -> None:  # pragma: no cover
    fields = (instance.source_file, instance.converted_file)

    def _do_cleanup() -> None:
        for field in fields:
            if field:
                try:
                    field.delete(save=False)
                except Exception:
                    logger.exception("清理 item 文件失败: %s", instance.id)

    transaction.on_commit(_do_cleanup)
