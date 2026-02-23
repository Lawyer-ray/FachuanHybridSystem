"""Business logic services."""

import uuid
from datetime import datetime
from typing import Any

from apps.core.path import Path


def ensure_output_dir() -> Any:
    from django.conf import settings
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        raise RuntimeError("MEDIA_ROOT 未配置")
    output_dir = Path(str(media_root)) / "image_rotation"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def build_zip_filename(*, prefix: str = "rotated_images") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique_id}.zip"


def build_pdf_filename(*, prefix: str = "rotated_pages") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.pdf"


def to_media_url(filename: str) -> str:
    return f"/media/image_rotation/{filename}"
