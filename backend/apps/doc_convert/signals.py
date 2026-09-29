"""要素式转换记录的文件清理信号。

记录删除时连带清理产物物理文件（FileField 不会自动删文件）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.doc_convert.models import DocConvertRecord

logger = logging.getLogger("apps.doc_convert")


@receiver(post_delete, sender=DocConvertRecord, dispatch_uid="cleanup_doc_convert_record_file")
def cleanup_doc_convert_record_file(
    sender: type, instance: DocConvertRecord, **kwargs: Any
) -> None:  # pragma: no cover
    from django.db import transaction

    output_file = instance.output_file

    def _do_cleanup() -> None:
        if not output_file:
            return
        try:
            output_file.delete(save=False)
        except Exception:
            logger.exception("清理要素式转换产物失败: record_id=%s", instance.id)

    transaction.on_commit(_do_cleanup)
