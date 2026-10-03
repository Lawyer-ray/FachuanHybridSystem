"""PDF 生成。"""

import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from numpy.typing import NDArray
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.filesystem.upload_paths import MediaEntity


def generate_a4_pdf(
    front_image: NDArray[np.uint8],
    back_image: NDArray[np.uint8],
    *,
    id_card_aspect_ratio: float,
    logger: Any,
) -> str:  # pragma: no cover
    width, height = A4

    card_width = 150 * mm
    card_height = card_width / id_card_aspect_ratio

    x = (width - card_width) / 2
    gap = 20 * mm
    total_height = card_height * 2 + gap
    start_y = (height - total_height) / 2
    y_back = start_y
    y_front = start_y + card_height + gap

    unique_id = uuid.uuid4().hex[:12]
    pdf_filename = f"merged_{unique_id}.pdf"

    # 中间图片与 PDF 渲染均在系统临时目录完成，最终产物经 default_storage 落盘
    buffer = BytesIO()
    with tempfile.TemporaryDirectory(prefix="id_card_merge_") as tmp_dir:
        front_temp_path = Path(tmp_dir) / f"front_pdf_{unique_id}.jpg"
        back_temp_path = Path(tmp_dir) / f"back_pdf_{unique_id}.jpg"
        cv2.imwrite(str(front_temp_path), front_image)
        cv2.imwrite(str(back_temp_path), back_image)

        c = canvas.Canvas(buffer, pagesize=A4)
        c.drawImage(
            str(front_temp_path),
            x,
            y_front,
            width=card_width,
            height=card_height,
            preserveAspectRatio=True,
            anchor="sw",
        )
        c.drawImage(
            str(back_temp_path),
            x,
            y_back,
            width=card_width,
            height=card_height,
            preserveAspectRatio=True,
            anchor="sw",
        )
        c.save()

    saved_path = default_storage.save(
        f"{MediaEntity.CLIENT_ID_CARDS}/{pdf_filename}",
        ContentFile(buffer.getvalue()),
    )
    logger.info(
        "PDF 生成成功",
        extra={"rel_path": saved_path, "size": f"{width}x{height}"},
    )
    return saved_path
