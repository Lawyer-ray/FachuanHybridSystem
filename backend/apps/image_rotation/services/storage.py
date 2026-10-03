"""Business logic services."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.utils import timezone

from apps.core.filesystem.upload_paths import MediaEntity


def export_rel_path(filename: str) -> str:
    """导出文件在 media 下的相对路径。"""
    return f"{MediaEntity.IMAGE_ROTATION}/{filename}"


def build_zip_filename(*, prefix: str = "rotated_images") -> str:
    timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique_id}.zip"


def build_pdf_filename(*, prefix: str = "rotated_pages") -> str:
    timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.pdf"


def to_media_url(filename: str) -> str:
    return f"{settings.MEDIA_URL}{MediaEntity.IMAGE_ROTATION}/{filename}"
