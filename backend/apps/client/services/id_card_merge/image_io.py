"""图片读写工具。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

from django.core.files.uploadedfile import UploadedFile

import cv2
import numpy as np
from numpy.typing import NDArray


def read_uploaded_image(image: UploadedFile, *, logger: Any) -> NDArray[np.uint8] | None:
    try:
        image.seek(0)
        file_bytes = image.read()
        image.seek(0)

        nparr = np.frombuffer(file_bytes, np.uint8)
        return cast(NDArray[np.uint8] | None, cv2.imdecode(nparr, cv2.IMREAD_COLOR))
    except Exception as e:
        logger.warning(
            "读取图片失败",
            extra={"file_name": getattr(image, "name", "unknown"), "error": str(e)},
        )
        return None


def save_temp_image(image: UploadedFile, *, prefix: str, temp_dir: Path, logger: Any) -> str:
    filename = getattr(image, "name", "image.jpg")
    ext = Path(filename).suffix
    if not ext:
        ext = ".jpg"

    unique_id = uuid.uuid4().hex[:12]
    temp_filename = f"{prefix}_{unique_id}{ext}"
    temp_path = temp_dir / temp_filename

    image.seek(0)
    temp_path.write_bytes(image.read())
    image.seek(0)

    logger.info(
        "临时图片保存成功",
        extra={"path": str(temp_path), "prefix": prefix},
    )
    return f"temp/{temp_filename}"
