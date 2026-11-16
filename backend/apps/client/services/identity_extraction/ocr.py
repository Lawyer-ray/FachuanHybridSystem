"""OCR 文字提取（图片 / 图片型 PDF 的 IO 路径）。

recognizer 与 ocr_service 由调用方按请求传入，本模块不持有状态。
"""

from __future__ import annotations

import logging
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.protocols import IOcrService

from .data_classes import OCRExtractionError

logger = logging.getLogger(__name__)


def _is_pdf_file(file_bytes: bytes) -> bool:  # pragma: no cover
    """检测文件是否为 PDF（魔数优先，fitz 试开兜底）。"""
    if not file_bytes or len(file_bytes) < 8:
        return False

    # PDF 文件通常以 %PDF- 开头,但可能有 BOM 或空白字符
    header = file_bytes[:1024]  # 检查前 1KB
    if b"%PDF-" in header:
        return True

    try:
        import pymupdf as fitz

        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return len(doc) > 0
    except Exception:
        return False


def _extract_from_image(image_bytes: bytes, ocr_service: IOcrService) -> str:  # pragma: no cover
    """从图片提取文字。"""
    from PIL import Image

    try:
        img: Any = Image.open(BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    except Exception as e:
        logger.exception("图片格式无效: %s", e)
        raise OCRExtractionError(_("图片格式无效,请上传 JPG 或 PNG 格式的图片")) from e

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
        img.save(tmp, format="JPEG", quality=95)
        tmp_path = tmp.name

        raw_text = ocr_service.recognize(tmp_path)

        if raw_text and raw_text.strip():
            logger.info("OCR 提取成功,文字长度: %s", len(raw_text))
            return raw_text.strip()

        raise OCRExtractionError(_("OCR 未能提取到有效文字"))


def _extract_from_pdf(pdf_bytes: bytes, ocr_service: IOcrService) -> str:  # pragma: no cover
    """从 PDF 提取文字(图片型PDF)。"""
    import pymupdf as fitz
    from PIL import Image

    # 禁用 PIL 的解压炸弹检查，避免超大 PDF 页面触发 DecompressionBombError
    Image.MAX_IMAGE_PIXELS = None

    all_texts = []

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            # 只处理前几页(证件通常只有1-2页)
            max_pages = min(len(doc), 3)
            for page_num in range(max_pages):
                page_text = _ocr_single_page(doc[page_num], ocr_service)
                if page_text:
                    all_texts.append(page_text)

        if all_texts:
            raw_text = "\n".join(all_texts)
            logger.info("PDF OCR 提取成功,文字长度: %s", len(raw_text))
            return raw_text.strip()

        raise OCRExtractionError(_("PDF OCR 未能提取到有效文字"))

    except OCRExtractionError:
        raise
    except (OSError, ValueError) as e:
        logger.exception("PDF 处理失败: %s", e)
        raise OCRExtractionError(_("PDF 处理失败: %(e)s") % {"e": e}) from e


def _ocr_single_page(page: Any, ocr_service: IOcrService) -> str:
    """渲染单页为图片并 OCR，返回文本或空字符串。"""
    import pymupdf as fitz

    mat = fitz.Matrix(300 / 72, 300 / 72)
    pix = page.get_pixmap(matrix=mat)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        pix.save(tmp.name)
        tmp_path = tmp.name
    try:
        return ocr_service.recognize(tmp_path) or ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)
