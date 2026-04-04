from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from apps.automation.services.ocr import OCRService
from apps.express_query.models import ExpressCarrierType

logger = logging.getLogger("apps.express_query")


@dataclass(frozen=True)
class TrackingExtractionResult:
    carrier_type: str
    tracking_number: str
    ocr_text: str


class TrackingExtractionService:
    _sf_pattern = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
    _ems_pattern = re.compile(r"(?<!\d)\d{13}(?!\d)")

    def __init__(self, ocr_service: OCRService | None = None) -> None:
        self._ocr_service = ocr_service or OCRService(use_v5=True)

    def extract(self, waybill_file_path: Path) -> TrackingExtractionResult:
        image_bytes = self._load_waybill_bytes_for_ocr(waybill_file_path)
        ocr_result = self._ocr_service.extract_text(image_bytes)
        full_text = ocr_result.text or ""

        candidate = self._pick_tracking_number(full_text)
        if candidate is None:
            logger.warning("未识别到运单号", extra={"file": str(waybill_file_path)})
            return TrackingExtractionResult(
                carrier_type=ExpressCarrierType.UNKNOWN,
                tracking_number="",
                ocr_text=full_text,
            )

        return TrackingExtractionResult(
            carrier_type=candidate["carrier"],
            tracking_number=candidate["tracking_number"],
            ocr_text=full_text,
        )

    def _load_waybill_bytes_for_ocr(self, waybill_file_path: Path) -> bytes:
        suffix = waybill_file_path.suffix.lower()
        if suffix != ".pdf":
            return waybill_file_path.read_bytes()

        import fitz

        with fitz.open(str(waybill_file_path)) as document:
            if document.page_count <= 0:
                raise ValueError("PDF 文件没有可识别页面")
            first_page = document.load_page(0)
            pixmap = first_page.get_pixmap(dpi=220)
            image_bytes = cast(bytes, pixmap.tobytes("png"))
            return image_bytes

    @staticmethod
    def truncate_pdf_to_first_page(pdf_path: Path) -> bool:
        """
        将多页 PDF 截断为仅保留第一页，节省存储空间。
        如果 PDF 只有一页则不操作。返回 True 表示已截断。
        """
        import fitz

        if pdf_path.suffix.lower() != ".pdf":
            return False

        try:
            doc = fitz.open(str(pdf_path))
            try:
                if doc.page_count <= 1:
                    return False

                first_page = doc.load_page(0)
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=0, to_page=0)
                page_count: int = doc.page_count

                temp_path = pdf_path.with_suffix(".tmp.pdf")
                new_doc.save(str(temp_path), garbage=4, deflate=True)
                new_doc.close()
                doc.close()

                temp_path.replace(pdf_path)
                logger.info(
                    "PDF 已截断为第 1 页（原 %d 页）: %s",
                    page_count,
                    pdf_path.name,
                )
                return True
            finally:
                # 确保无论成功失败都关闭文档
                try:
                    new_doc.close()
                except Exception:
                    pass
                try:
                    doc.close()
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("PDF 截断失败（不影响后续流程）: %s", exc)
            return False

    def _pick_tracking_number(self, text: str) -> dict[str, str] | None:
        if not text:
            return None

        normalized = text.replace("|", " ")
        candidates: list[dict[str, str | int]] = []

        # 先收集所有顺丰单号的位置范围，避免EMS匹配到顺丰单号中的数字部分
        sf_ranges: list[tuple[int, int]] = []
        for match in self._sf_pattern.finditer(normalized):
            tracking_number = match.group(0).upper().strip()
            candidates.append(
                {
                    "carrier": ExpressCarrierType.SF,
                    "tracking_number": tracking_number,
                    "position": match.start(),
                }
            )
            sf_ranges.append((match.start(), match.end()))

        for match in self._ems_pattern.finditer(normalized):
            # 检查EMS匹配位置是否与顺丰单号重叠
            ems_start = match.start()
            ems_end = match.end()

            # 如果EMS匹配在某个顺丰单号的范围内，则跳过
            is_overlapping = any(
                sf_start <= ems_start < sf_end or sf_start < ems_end <= sf_end for sf_start, sf_end in sf_ranges
            )

            if is_overlapping:
                continue

            tracking_number = match.group(0).upper().strip()
            candidates.append(
                {
                    "carrier": ExpressCarrierType.EMS,
                    "tracking_number": tracking_number,
                    "position": match.start(),
                }
            )

        if not candidates:
            return None

        selected = sorted(candidates, key=lambda item: int(item["position"]))[0]
        return {
            "carrier": str(selected["carrier"]),
            "tracking_number": str(selected["tracking_number"]),
        }
