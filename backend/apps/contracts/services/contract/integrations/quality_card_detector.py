"""律师办案服务质量监督卡检测。"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_QUALITY_CARD_KEYWORD = "律师办案服务质量监督卡"


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _extract_last_page_text_direct(file_path: Path) -> str:
    try:
        with fitz.open(file_path.as_posix()) as doc:
            if doc.page_count <= 0:
                return ""
            page = doc.load_page(doc.page_count - 1)
            return str(page.get_text() or "")
    except (OSError, RuntimeError):
        logger.exception("quality_card_check_direct_failed", extra={"path": file_path.as_posix()})
        return ""


def _extract_last_page_text_with_ocr(file_path: Path) -> str:
    try:
        from apps.automation.services.document.document_processing import extract_text_from_image_with_rapidocr

        with fitz.open(file_path.as_posix()) as doc:
            if doc.page_count <= 0:
                return ""
            page = doc.load_page(doc.page_count - 1)
            pix = page.get_pixmap()

            with tempfile.NamedTemporaryFile(prefix="contract_last_page_", suffix=".png", delete=False) as tmp:
                temp_path = Path(tmp.name)
            try:
                pix.save(temp_path.as_posix())
                return str(extract_text_from_image_with_rapidocr(temp_path.as_posix()) or "")
            finally:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
    except (OSError, RuntimeError):
        logger.exception("quality_card_check_ocr_failed", extra={"path": file_path.as_posix()})
        return ""


def has_quality_card_on_last_page(file_path: Path) -> bool:
    """检测 PDF 最一页是否包含监督卡。"""
    keyword = _normalize_for_match(_QUALITY_CARD_KEYWORD)
    if not keyword:
        return False

    direct_text = _extract_last_page_text_direct(file_path)
    if keyword in _normalize_for_match(direct_text):
        return True

    ocr_text = _extract_last_page_text_with_ocr(file_path)
    return keyword in _normalize_for_match(ocr_text)
