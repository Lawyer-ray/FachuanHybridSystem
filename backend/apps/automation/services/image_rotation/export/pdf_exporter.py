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
            img_w, img_h = img.size
            # 使用 A4 点数 (595×842)，保持图片宽高比居中
            page_w, page_h = 595, 842
            scale = min(page_w / img_w, page_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            x0 = (page_w - draw_w) / 2
            y0 = (page_h - draw_h) / 2
            page = pdf_doc.new_page(width=page_w, height=page_h)
            rect = fitz.Rect(x0, y0, x0 + draw_w, y0 + draw_h)
            page.insert_image(rect, stream=rotated_image_bytes)
        return pdf_doc.tobytes()
    finally:
        pdf_doc.close()
