"""Contracts 模块信号处理器。

处理合同相关模型删除时的物理文件清理。
兜底方案：service 层的 delete 方法已做清理，但 cascade 删除或直接 ORM 删除会绕过 service 层。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.contracts")


@receiver(post_delete, sender="contracts.FinalizedMaterial")
def _cleanup_finalized_material_file(sender: Any, instance: Any, **kwargs: Any) -> None:  # pragma: no cover
    """删除 FinalizedMaterial 时清理物理文件。"""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return
    # 收敛校验延迟到 _unlink_material 内执行（on_commit 后），此处仅传递原始字符串
    transaction.on_commit(lambda fp=file_path, mid=instance.pk: _unlink_material(fp, mid))  # type: ignore[misc]  # mypy 对带默认参 lambda 的推断限制


def _unlink_material(file_path: str, material_id: int) -> None:
    """收敛校验后清理归档材料物理文件。

    安全审计（2026-10-19）：file_path 可能是历史脏数据中的任意绝对路径 / 含 ".." 的值，
    禁止直拼 MEDIA_ROOT 后 unlink（绝对路径会原样保留导致误删任意文件）。
    统一经 ``to_media_abs`` 收敛到 MEDIA_ROOT 内，越界跳过物理删除并 warning（不抛）。
    """
    from apps.core.exceptions import ValidationException
    from apps.core.services.storage_service import to_media_abs

    try:
        abs_path = to_media_abs(file_path)
    except ValidationException:
        logger.warning(
            "post_delete: 归档材料路径非法/越界，跳过物理删除",
            extra={"material_id": material_id, "file_path": file_path},
        )
        return
    try:
        if abs_path.exists():
            abs_path.unlink()
            logger.info(
                "post_delete: 已清理归档材料文件",
                extra={"material_id": material_id, "file_path": file_path},
            )
    except (OSError, ValueError):
        logger.exception(
            "post_delete: 清理归档材料文件失败",
            extra={"material_id": material_id, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.Invoice")
def _cleanup_invoice_file(sender: Any, instance: Any, **kwargs: Any) -> None:  # pragma: no cover
    """删除 Invoice 时清理物理文件。"""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return
    transaction.on_commit(lambda fp=file_path, mid=instance.pk: _delete_invoice_file(fp, mid))  # type: ignore[misc]  # mypy 对带默认参 lambda 的推断限制


def _delete_invoice_file(file_path: str, invoice_id: int) -> None:
    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(file_path)
        logger.info(
            "post_delete: 已清理发票文件",
            extra={"invoice_id": invoice_id, "file_path": file_path},
        )
    except Exception:
        logger.exception(
            "post_delete: 清理发票文件失败",
            extra={"invoice_id": invoice_id, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.ClientPaymentRecord")
def _cleanup_client_payment_image(sender: Any, instance: Any, **kwargs: Any) -> None:  # pragma: no cover
    """删除 ClientPaymentRecord 时清理凭证图片。"""
    image_path = getattr(instance, "image_path", "")
    if not image_path:
        return
    transaction.on_commit(lambda ip=image_path, mid=instance.pk: _delete_payment_image(ip, mid))  # type: ignore[misc]  # mypy 对带默认参 lambda 的推断限制


def _delete_payment_image(image_path: str, record_id: int) -> None:
    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(image_path)
        logger.info(
            "post_delete: 已清理回款凭证图片",
            extra={"record_id": record_id, "image_path": image_path},
        )
    except Exception:
        logger.exception(
            "post_delete: 清理回款凭证图片失败",
            extra={"record_id": record_id, "image_path": image_path},
        )
