"""OCR 触发判据测试（pymupdf 合成 PDF + mock OCR，不碰数据库）。

锁住报告 §3.C.0 的断层修复：
- 扫描页只要有 ≥20 字印章语就永不 OCR（旧 bug）→ 现在整页大图+文字极少会 OCR；
- 正常电子页（无整页大图，或图文混排文字 ≥200）不会白 OCR。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf as fitz

from apps.litigation_ai.services.evidence.evidence_text_extraction_service import (
    EvidenceTextExtractionService,
    _image_coverage,
    _needs_ocr,
)

_STAMP = "已核对与原件相符扫描件与留档资料相符经办人张某某罗某某"  # >20 字印章语
_BODY = "本合同约定甲方向乙方支付借款人民币伍拾万元整利率按年利率计算" * 20  # 远超 200 字


def _make_pdf(path: Path, *, text: str = "", full_image: bool = False, small_image: bool = False) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if full_image or small_image:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 80))
        pix.set_rect(pix.irect, (180, 180, 180))
        rect = page.rect if full_image else fitz.Rect(0, 0, 100, 100)
        page.insert_image(rect, pixmap=pix)
    if text:
        page.insert_textbox(fitz.Rect(40, 40, 555, 800), text, fontsize=11, fontname="china-s")
    doc.save(str(path))
    doc.close()


def _page(path: Path):
    return fitz.open(str(path)).load_page(0)


class TestNeedsOcr:
    def test_electronic_page_no_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "elec.pdf"
        _make_pdf(p, text=_BODY)
        page = _page(p)
        assert _image_coverage(page) < 0.5
        assert _needs_ocr(page, _BODY) is False

    def test_scanned_page_with_stamp_triggers_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "scan.pdf"
        _make_pdf(p, text=_STAMP, full_image=True)
        page = _page(p)
        assert len(_STAMP) >= 20  # 旧判据会漏掉这页
        assert _image_coverage(page) >= 0.5
        assert _needs_ocr(page, _STAMP) is True

    def test_image_heavy_electronic_page_no_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "img_elec.pdf"
        _make_pdf(p, text=_BODY, full_image=True)
        page = _page(p)
        assert _image_coverage(page) >= 0.5
        assert _needs_ocr(page, _BODY) is False  # 文字 ≥200，不白 OCR

    def test_blank_page_triggers_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "blank.pdf"
        _make_pdf(p)
        assert _needs_ocr(_page(p), "") is True

    def test_small_image_short_text_no_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "small.pdf"
        _make_pdf(p, text=_STAMP, small_image=True)
        page = _page(p)
        assert _image_coverage(page) < 0.5
        assert _needs_ocr(page, _STAMP) is False


class TestExtractChunksIntegration:
    def test_scanned_stamp_page_uses_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "scan.pdf"
        _make_pdf(p, text=_STAMP, full_image=True)
        ocr = MagicMock()
        ocr.recognize_bytes.return_value = "OCR 识别出的合同全文"
        with patch("apps.litigation_ai.dependencies.get_ocr_service", return_value=ocr):
            chunks = EvidenceTextExtractionService().extract_chunks(str(p))
        assert len(chunks) == 1
        assert chunks[0]["extraction_method"] == "ocr"
        assert chunks[0]["text"] == "OCR 识别出的合同全文"
        ocr.recognize_bytes.assert_called_once()

    def test_electronic_page_skips_ocr(self, tmp_path: Path) -> None:
        p = tmp_path / "elec.pdf"
        _make_pdf(p, text=_BODY)
        ocr = MagicMock()
        with patch("apps.litigation_ai.dependencies.get_ocr_service", return_value=ocr):
            chunks = EvidenceTextExtractionService().extract_chunks(str(p))
        assert chunks[0]["extraction_method"] == "text"
        ocr.recognize_bytes.assert_not_called()
