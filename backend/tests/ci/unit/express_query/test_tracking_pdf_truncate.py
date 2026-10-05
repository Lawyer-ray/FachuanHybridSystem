"""TrackingExtractionService.truncate_pdf_to_first_page 单元测试（本地临时 PDF）。"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from apps.express_query.services.tracking_extraction_service import TrackingExtractionService


def _make_pdf(path: Path, pages: int) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page-{index + 1}")
    doc.save(str(path))
    doc.close()


class TestTruncatePdfToFirstPage:
    def test_non_pdf_suffix_returns_false(self, tmp_path: Path):
        target = tmp_path / "waybill.png"
        assert TrackingExtractionService.truncate_pdf_to_first_page(target) is False

    def test_single_page_pdf_not_truncated(self, tmp_path: Path):
        target = tmp_path / "waybill.pdf"
        _make_pdf(target, pages=1)

        result = TrackingExtractionService.truncate_pdf_to_first_page(target)

        assert result is False
        with fitz.open(str(target)) as doc:
            assert doc.page_count == 1

    def test_multi_page_pdf_truncated_to_one(self, tmp_path: Path):
        target = tmp_path / "waybill.pdf"
        _make_pdf(target, pages=3)

        result = TrackingExtractionService.truncate_pdf_to_first_page(target)

        assert result is True
        with fitz.open(str(target)) as doc:
            assert doc.page_count == 1
            assert "page-1" in doc.load_page(0).get_text()
        # 临时文件已清理，目录中只剩原文件
        assert [p.name for p in tmp_path.iterdir()] == ["waybill.pdf"]

    def test_corrupt_pdf_returns_false_without_raising(self, tmp_path: Path):
        target = tmp_path / "waybill.pdf"
        target.write_bytes(b"not a real pdf")

        result = TrackingExtractionService.truncate_pdf_to_first_page(target)

        assert result is False
