"""Business logic services."""

import logging
from typing import Any

logger = logging.getLogger("apps.litigation_ai")


class EvidenceTextExtractionService:
    def extract_chunks(self, file_path: str, max_pages: int | None = None) -> list[dict[str, Any]]:
        import fitz

        doc = fitz.open(file_path)
        results: list[dict[str, Any]] = []

        from apps.litigation_ai.dependencies import get_ocr_recognizer

        ocr = get_ocr_recognizer()

        page_count = doc.page_count
        limit = min(page_count, max_pages) if max_pages else page_count

        for i in range(limit):
            page = doc.load_page(i)
            text = (page.get_text("text") or "").strip()
            method = "text"

            if len(text) < 20:
                try:
                    pix = page.get_pixmap(dpi=200)
                    png_bytes = pix.tobytes("png")
                    ocr_text = (ocr.recognize_bytes(png_bytes) or "").strip()
                    if ocr_text:
                        text = ocr_text
                        method = "ocr"
                except Exception as e:
                    logger.warning(f"OCR 失败: {e}", exc_info=True)

            if text:
                results.append(
                    {
                        "page_start": i + 1,
                        "page_end": i + 1,
                        "text": text,
                        "extraction_method": method,
                    }
                )

        return results
