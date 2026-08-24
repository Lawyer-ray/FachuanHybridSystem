"""模型信号：清理 FileField 关联的物理文件。"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.labor_arbitration.models.document import ArbitrationDocumentImage

logger = logging.getLogger(__name__)


def register_signals() -> None:
    """注册信号（在 AppConfig.ready 中调用）。"""

    @receiver(post_delete, sender=ArbitrationDocumentImage)
    def _delete_image_file(sender: type, instance: ArbitrationDocumentImage, **kwargs: object) -> None:
        if instance.image:
            try:
                instance.image.delete(save=False)
            except Exception as exc:  # pragma: no cover
                logger.warning("删除仲裁文书图片文件失败: %s", exc)
