"""Business logic services."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("apps.litigation_ai")

#: 文本层少于该字符数视为「无有效文字层」（原阈值，保留）。
_MIN_TEXT_CHARS = 20
#: 扫描页判据：整页图像覆盖率 ≥ 该值 且 文本层 < _SCAN_MAX_TEXT_CHARS。
#: 旧「<20 字才 OCR」会被扫描页上的印章核验语（「已核对与原件相符…」约 45 字）
#: 骗过——永不 OCR，chunk 里只剩印章语。改用「整页大图 + 文字极少」双判据：
#: 正常电子页要么无整页大图（覆盖率 0），要么图文混排文字 ≥200，不会白 OCR。
_SCAN_IMAGE_COVERAGE = 0.5
_SCAN_MAX_TEXT_CHARS = 200


def _image_coverage(page: Any) -> float:
    """页面被图像覆盖的面积占比（重叠图按面积和近似，封顶 1.0）。"""
    page_area = float(page.rect.width) * float(page.rect.height)
    if page_area <= 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        bbox = info.get("bbox")
        if bbox:
            covered += max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
    return min(covered / page_area, 1.0)


def _needs_ocr(page: Any, text: str) -> bool:
    if len(text) < _MIN_TEXT_CHARS:
        return True
    return _image_coverage(page) >= _SCAN_IMAGE_COVERAGE and len(text) < _SCAN_MAX_TEXT_CHARS


class EvidenceTextExtractionService:
    def extract_chunks(self, file_path: str, max_pages: int | None = None) -> list[dict[str, Any]]:  # pragma: no cover
        import pymupdf as fitz

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

            if _needs_ocr(page, text):
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

    def _try_ocr_fallback(self, page: Any, ocr: Any) -> str:
        """渲染页面为图片并 OCR，返回文本或空字符串。"""
        try:
            pix = page.get_pixmap(dpi=200)
            png_bytes = pix.tobytes("png")
            return (ocr.recognize_bytes(png_bytes) or "").strip()
        except Exception as e:
            logger.warning("OCR 失败: %s", e, exc_info=True)
            return ""

    async def aextract_chunks(
        self, file_path: str, max_pages: int | None = None
    ) -> list[dict[str, Any]]:  # pragma: no cover
        """异步版本 — 将 PDF 解析和 OCR 卸载到线程池."""
        return await asyncio.to_thread(self.extract_chunks, file_path, max_pages)
