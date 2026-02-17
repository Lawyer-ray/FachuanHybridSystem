"""Business logic services."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import cv2
import numpy as np
from django.core.files.uploadedfile import UploadedFile

from apps.core.path import Path

logger = logging.getLogger(__name__)


def read_uploaded_image(image: UploadedFile, *, logger: Any) -> np.ndarray | None | None:  # type: ignore[type-arg]
    try:
        image.seek(0)
        file_bytes = image.read()
        image.seek(0)

        nparr = np.frombuffer(file_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.warning(
            "读取图片失败",
            extra={"file_name": getattr(image, "name", "unknown"), "error": str(e)},
        )
        return None


def save_temp_image(image: UploadedFile, *, prefix: str, temp_dir: Path, logger) -> str:  # type: ignore[no-untyped-def]
    filename = getattr(image, "name", "image.jpg")
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".jpg"

    unique_id = uuid.uuid4().hex[:12]
    temp_filename = f"{prefix}_{unique_id}{ext}"
    temp_path = temp_dir / temp_filename

    image.seek(0)
    with open(temp_path, "wb") as f:
        for chunk in image.chunks():
            f.write(chunk)
    image.seek(0)

    logger.info(
        "临时图片保存成功",
        extra={"path": str(temp_path), "prefix": prefix},
    )
    return f"temp/{temp_filename}"
