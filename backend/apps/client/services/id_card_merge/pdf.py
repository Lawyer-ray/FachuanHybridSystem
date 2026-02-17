"""Business logic services."""

import logging
import os
import uuid
from typing import Any

import cv2
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.path import Path

logger = logging.getLogger(__name__)


def generate_a4_pdf(
    front_image: np.ndarray,  # type: ignore[type-arg]
    back_image: np.ndarray,  # type: ignore[type-arg]
    *,
    id_card_aspect_ratio: float,
    output_dir: Path,
    temp_dir: Path,
    logger: Any,
) -> str:
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
    pdf_path = output_dir / pdf_filename

    front_temp_path = temp_dir / f"front_pdf_{unique_id}.jpg"
    back_temp_path = temp_dir / f"back_pdf_{unique_id}.jpg"

    try:
        cv2.imwrite(str(front_temp_path), front_image)
        cv2.imwrite(str(back_temp_path), back_image)

        c = canvas.Canvas(str(pdf_path), pagesize=A4)
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

        logger.info(
            "PDF 生成成功",
            extra={"pdf_path": str(pdf_path), "size": f"{width}x{height}"},
        )
        return f"id_card_merged/{pdf_filename}"
    finally:
        if front_temp_path.exists():
            try:
                os.remove(str(front_temp_path))
            except OSError as e:
                logger.warning(
                    "清理临时文件失败",
                    extra={"file": str(front_temp_path), "error": str(e)},
                )

        if back_temp_path.exists():
            try:
                os.remove(str(back_temp_path))
            except OSError as e:
                logger.warning(
                    "清理临时文件失败",
                    extra={"file": str(back_temp_path), "error": str(e)},
                )
