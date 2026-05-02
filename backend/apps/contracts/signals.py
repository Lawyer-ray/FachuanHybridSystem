"""Contracts 模块信号处理器。

处理合同相关模型删除时的物理文件清理。
兜底方案：service 层的 delete 方法已做清理，但 cascade 删除或直接 ORM 删除会绕过 service 层。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.contracts")


@receiver(post_delete, sender="contracts.FinalizedMaterial")
def _cleanup_finalized_material_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 FinalizedMaterial 时清理物理文件。"""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return
    try:
        abs_path = Path(settings.MEDIA_ROOT) / file_path
        if abs_path.exists():
            abs_path.unlink()
            logger.info(
                "post_delete: 已清理归档材料文件",
                extra={"material_id": instance.pk, "file_path": file_path},
            )
    except Exception:
        logger.exception(
            "post_delete: 清理归档材料文件失败",
            extra={"material_id": instance.pk, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.Invoice")
def _cleanup_invoice_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 Invoice 时清理物理文件。"""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return
    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(file_path)
        logger.info(
            "post_delete: 已清理发票文件",
            extra={"invoice_id": instance.pk, "file_path": file_path},
        )
    except Exception:
        logger.exception(
            "post_delete: 清理发票文件失败",
            extra={"invoice_id": instance.pk, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.ClientPaymentRecord")
def _cleanup_client_payment_image(sender: Any, instance: Any, **kwargs: Any) -> None:
    """删除 ClientPaymentRecord 时清理凭证图片。"""
    image_path = getattr(instance, "image_path", "")
    if not image_path:
        return
    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(image_path)
        logger.info(
            "post_delete: 已清理回款凭证图片",
            extra={"record_id": instance.pk, "image_path": image_path},
        )
    except Exception:
        logger.exception(
            "post_delete: 清理回款凭证图片失败",
            extra={"record_id": instance.pk, "image_path": image_path},
        )
