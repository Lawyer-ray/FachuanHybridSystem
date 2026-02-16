"""Business logic services."""

import uuid
from datetime import datetime
from typing import Any

from apps.core.config import get_config
from apps.core.path import Path


def ensure_output_dir() -> Any:
    media_root = get_config("django.media_root", None)
    if not media_root:
        raise RuntimeError("django.media_root 未配置")
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
