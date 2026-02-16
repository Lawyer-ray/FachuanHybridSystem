"""Business logic services."""

import io
import logging
from typing import Any

import fitz
from PIL import Image

from apps.automation.services.image_rotation import storage
from apps.automation.services.image_rotation.transform import apply_rotation_for_pdf
from apps.core.path import Path

logger = logging.getLogger("apps.automation.image_rotation")


def generate_pdf(*, processed_images: list[tuple[bytes, int]], output_dir: Path) -> str:
    pdf_filename = storage.build_pdf_filename()
    pdf_path = output_dir / pdf_filename

    try:
        pdf_bytes = _create_pdf_from_images(processed_images)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        logger.info(
            "PDF 文件生成成功",
            extra={
                "pdf_path": str(pdf_path),
                "page_count": len(processed_images),
            },
        )
        return storage.to_media_url(pdf_filename)
    except Exception:
        if pdf_path.exists():
            pdf_path.unlink()
        raise


def _create_pdf_from_images(images: list[tuple[bytes, int]]) -> Any:
    pdf_doc = fitz.open()
    try:
        for image_bytes, rotation in images:
            rotated_image_bytes = apply_rotation_for_pdf(image_bytes, rotation)
            img = Image.open(io.BytesIO(rotated_image_bytes))
            width, height = img.size
            page = pdf_doc.new_page(width=width, height=height)
            rect = fitz.Rect(0, 0, width, height)
            page.insert_image(rect, stream=rotated_image_bytes)
        return pdf_doc.tobytes()
    finally:
        pdf_doc.close()
