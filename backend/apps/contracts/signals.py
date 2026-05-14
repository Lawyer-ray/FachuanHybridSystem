"""Contracts signal handlers for physical file cleanup."""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger("apps.contracts")


@receiver(post_delete, sender="contracts.FinalizedMaterial")
def _cleanup_finalized_material_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Cleanup finalized material file after ORM-level delete."""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return

    try:
        from apps.contracts.services.contract.integrations.material_service import MaterialService

        MaterialService().delete_material_file(instance)
        logger.info(
            "post_delete: cleaned finalized material file",
            extra={"material_id": instance.pk, "file_path": file_path},
        )
    except Exception:
        logger.exception(
            "post_delete: failed to cleanup finalized material file",
            extra={"material_id": instance.pk, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.Invoice")
def _cleanup_invoice_file(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Cleanup invoice physical file after delete."""
    file_path = getattr(instance, "file_path", "")
    if not file_path:
        return

    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(file_path)
        logger.info(
            "post_delete: cleaned invoice file",
            extra={"invoice_id": instance.pk, "file_path": file_path},
        )
    except Exception:
        logger.exception(
            "post_delete: failed to cleanup invoice file",
            extra={"invoice_id": instance.pk, "file_path": file_path},
        )


@receiver(post_delete, sender="contracts.ClientPaymentRecord")
def _cleanup_client_payment_image(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Cleanup client payment proof image after delete."""
    image_path = getattr(instance, "image_path", "")
    if not image_path:
        return

    try:
        from apps.core.services import storage_service as storage

        storage.delete_media_file(image_path)
        logger.info(
            "post_delete: cleaned client payment image",
            extra={"record_id": instance.pk, "image_path": image_path},
        )
    except Exception:
        logger.exception(
            "post_delete: failed to cleanup client payment image",
            extra={"record_id": instance.pk, "image_path": image_path},
        )
