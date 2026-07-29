"""Business logic services."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("apps.litigation_ai")


class EvidenceTextExtractionService:
    def extract_chunks(self, file_path: str, max_pages: int | None = None) -> list[dict[str, Any]]:  # pragma: no cover
        import fitz

        doc = fitz.open(file_path)
        results: list[dict[str, Any]] = []

        from apps.litigation_ai.dependencies import get_ocr_service

        ocr = get_ocr_service()

        page_count = doc.page_count
        limit = min(page_count, max_pages) if max_pages else page_count

        for i in range(limit):
            page = doc.load_page(i)
            text = (page.get_text("text") or "").strip()
            method = "text"

            if len(text) < 20:
                ocr_text = self._try_ocr_fallback(page, ocr)
                if ocr_text:
                    text = ocr_text
                    method = "ocr"

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

    def _try_ocr_fallback(self, page: Any, ocr: Any) -> str:  # type: ignore[no-untyped-def]
        """渲染页面为图片并 OCR，返回文本或空字符串。"""
        try:
            pix = page.get_pixmap(dpi=200)
            png_bytes = pix.tobytes("png")
            return (ocr.recognize_bytes(png_bytes) or "").strip()
        except Exception as e:
            logger.warning(f"OCR 失败: {e}", exc_info=True)
            return ""

    async def aextract_chunks(
        self, file_path: str, max_pages: int | None = None
    ) -> list[dict[str, Any]]:  # pragma: no cover
        """异步版本 — 将 PDF 解析和 OCR 卸载到线程池."""
        return await asyncio.to_thread(self.extract_chunks, file_path, max_pages)
