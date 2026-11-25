"""基线捕获「读」这一半的单测：字节流 → 页数 / 逐页指纹 / 文本层。

所有样本都在用例里**现场合成**（PyMuPDF / python-docx 造字节流），
不读仓库或 /tmp 下的任何真实案卷——真实材料一旦进测试，断言就会随某份文件变化。

为什么合成扫描件只画图不写字：这就是「无文本层」的定义。基线侧绝不允许 OCR，
所以 ``text`` 必须为空串，且这条事实要被锁住（否则有人给基线加个 OCR 兜底
就能让「扫描件永远核不上」变成「扫描件天天误报」）。
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Sequence

import docx
import pymupdf
import pytest

from apps.doc_verify.services.anchor.extract import detect_document_kind, extract_document
from apps.pdf_splitting.services.split.page_fingerprint import SAME_PAGE_MAX_DISTANCE, signature_distance

_LOGGER_NAME = "apps.doc_verify.services.anchor.extract"


def _make_digital_pdf(page_texts: Sequence[str]) -> bytes:
    """合成数字 PDF：每页一行 ASCII 文字（Helvetica 不含中文，避免嵌入字体）。"""
    document = pymupdf.open()
    for index, body in enumerate(page_texts, start=1):
        page = document.new_page()
        page.insert_text((72, 100), f"page {index}: {body}", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _make_scanned_pdf(page_count: int = 2) -> bytes:
    """合成扫描件：只有图形、**没有任何文字**，即「无文本层」。"""
    document = pymupdf.open()
    for index in range(page_count):
        page = document.new_page()
        page.draw_rect(
            pymupdf.Rect(80 + index * 20, 120, 320, 260),
            color=(0, 0, 0),
            fill=(0.15, 0.15, 0.15),
        )
    data = document.tobytes()
    document.close()
    return data


def _make_docx(paragraphs: Sequence[str], table_rows: Sequence[Sequence[str]]) -> bytes:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for row_index, row in enumerate(table_rows):
            for col_index, value in enumerate(row):
                table.cell(row_index, col_index).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_png() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect(pymupdf.Rect(90, 140, 330, 240), color=(0, 0, 0), fill=(0.3, 0.3, 0.3))
    png = page.get_pixmap(dpi=100).tobytes("png")
    document.close()
    return png


class TestPdfExtract:
    def test_pdf_extract_returns_page_count_signatures_and_text(self) -> None:
        data = _make_digital_pdf(["alpha body", "beta body", "gamma body"])

        inbound = extract_document(data, "起诉状.pdf")

        assert inbound.page_count == 3
        assert len(inbound.page_signatures) == 3
        assert all(len(signature) > 0 for signature in inbound.page_signatures)
        assert "page 1: alpha body" in inbound.text
        assert "page 3: gamma body" in inbound.text
        assert inbound.sha256 == hashlib.sha256(data).hexdigest()
        assert inbound.file_name == "起诉状.pdf"

    def test_pdf_page_texts_are_separated_by_form_feed(self) -> None:
        """``\\f`` 是「第 i 段 == 第 i 页」的唯一保证，按页断言全靠它。"""
        data = _make_digital_pdf(["alpha body", "beta body", "gamma body"])

        inbound = extract_document(data, "起诉状.pdf")

        pages = inbound.text.split("\f")
        assert len(pages) == 3
        assert "beta body" in pages[1]
        assert "alpha body" not in pages[1]

    def test_scanned_pdf_has_empty_text_but_keeps_signatures(self, caplog: pytest.LogCaptureFixture) -> None:
        data = _make_scanned_pdf(page_count=2)

        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            inbound = extract_document(data, "扫描确认书.pdf")

        assert inbound.text == ""
        assert inbound.page_count == 2
        assert len(inbound.page_signatures) == 2
        assert "没有文本层" in caplog.text

    def test_corrupt_pdf_raises_value_error_with_file_name(self) -> None:
        with pytest.raises(ValueError, match="PDF 无法打开") as excinfo:
            extract_document(b"%PDF-1.7 truncated garbage", "坏件.pdf")

        assert "坏件.pdf" in str(excinfo.value)

    def test_empty_bytes_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="字节为空"):
            extract_document(b"", "空件.pdf")


class TestDocxExtract:
    def test_docx_extract_includes_paragraphs_and_table_cells(self) -> None:
        """签署页几乎总在表格里：只取段落会丢落款（日期 / 盖章人）。"""
        data = _make_docx(
            paragraphs=["授权委托书", "委托人：张三"],
            table_rows=[["受托人", "李四"], ["签约日期", "2026年11月25日"]],
        )

        inbound = extract_document(data, "授权委托书.docx")

        assert "委托人：张三" in inbound.text
        assert "2026年11月25日" in inbound.text
        # docx 不渲染：页数未知、图像指纹无从谈起，留空而不是猜
        assert inbound.page_count == 0
        assert inbound.page_signatures == ()
        assert inbound.sha256 == hashlib.sha256(data).hexdigest()

    def test_corrupt_docx_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Word 文档无法打开") as excinfo:
            extract_document(b"not a zip at all", "坏件.docx")

        assert "坏件.docx" in str(excinfo.value)


class TestVisualExtract:
    def test_image_has_fingerprint_but_no_text(self) -> None:
        data = _make_png()

        inbound = extract_document(data, "回传照片.png")

        assert inbound.text == ""
        assert inbound.page_count == 1
        assert len(inbound.page_signatures) == 1
        assert len(inbound.page_signatures[0]) > 0

    def test_unknown_bytes_degrade_to_sha_only(self, caplog: pytest.LogCaptureFixture) -> None:
        """未知格式「能算则算」：算不出指纹也要留下字节 SHA，且记一行 info 而不是静默。"""
        data = b"plain text, not a document"

        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            inbound = extract_document(data, "不认识的格式.bin")

        assert inbound.text == ""
        assert inbound.page_signatures == ()
        assert inbound.sha256 == hashlib.sha256(data).hexdigest()
        assert "无法解码" in caplog.text


class TestKindDetection:
    def test_pdf_magic_wins_over_wrong_suffix(self) -> None:
        data = _make_digital_pdf(["alpha body"])

        assert detect_document_kind(data, "被改名成.docx") == "pdf"


class TestFingerprintCrossRepresentation:
    def test_digital_render_and_reprinted_image_stay_within_same_page_threshold(self) -> None:
        """「同一页」0.03 容差成立的前提：数字渲染与「扫描件」的指纹要远小于它。

        本用例的「扫描」是合成口径（100dpi 数字页 → 150dpi PNG → 贴回 A4 页），
        不含真实扫描仪的歪斜 / 噪点 / 底色。实测距离 0.0001，比阈值小两个数量级，
        所以这里卡 0.01：既锁住前提，又给渲染实现变化留 100 倍余量。
        """
        digital_bytes = _make_digital_pdf(["alpha body"])
        digital_document = pymupdf.open(stream=digital_bytes, filetype="pdf")
        digital_signature = extract_document(digital_bytes, "起诉状.pdf").page_signatures[0]
        png = digital_document.load_page(0).get_pixmap(dpi=150).tobytes("png")
        digital_document.close()

        scanned_document = pymupdf.open()
        scanned_page = scanned_document.new_page()
        scanned_page.insert_image(scanned_page.rect, stream=png)
        scanned_bytes = scanned_document.tobytes()
        scanned_document.close()

        scanned_inbound = extract_document(scanned_bytes, "扫描回传.pdf")

        assert scanned_inbound.text == ""
        distance = signature_distance(digital_signature, scanned_inbound.page_signatures[0])
        assert distance < SAME_PAGE_MAX_DISTANCE
        assert distance < 0.01
