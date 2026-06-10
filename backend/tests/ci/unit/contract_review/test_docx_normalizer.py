"""DOCX format normalizer tests with mocked file operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer


class TestDocxFormatNormalizerInit:
    def test_init_default_output(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        assert normalizer.input_path == Path("/tmp/test.docx")
        assert "规范化" in str(normalizer.output_path)

    def test_init_custom_output(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx", output_path="/tmp/out.docx")
        assert normalizer.output_path == Path("/tmp/out.docx")

    def test_init_with_reference(self):
        normalizer = DocxFormatNormalizer(
            input_path="/tmp/test.docx", reference_path="/tmp/ref.docx"
        )
        assert normalizer.reference_path == Path("/tmp/ref.docx")

    def test_init_no_reference(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        assert normalizer.reference_path is None


class TestDocxFormatNormalizerFallback:
    def test_fallback_classify_bold_short(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        para = MagicMock()
        para.text = "合同条款"
        para.runs = [MagicMock()]
        rPr = MagicMock()
        rPr.find.return_value = MagicMock()  # bold element exists
        para.runs[0]._element.find.return_value = rPr
        level = normalizer._fallback_classify(para)
        assert level == 0

    def test_fallback_classify_chinese_number(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        para = MagicMock()
        para.text = "一、合同标的"
        para.runs = []
        level = normalizer._fallback_classify(para)
        assert level == 0

    def test_fallback_classify_sub_number(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        para = MagicMock()
        para.text = "1、标的物名称"
        para.runs = []
        level = normalizer._fallback_classify(para)
        assert level == 2

    def test_fallback_classify_body(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        para = MagicMock()
        para.text = "这是一段普通的合同正文内容"
        para.runs = []
        level = normalizer._fallback_classify(para)
        assert level == 1

    def test_fallback_classify_empty(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        para = MagicMock()
        para.text = ""
        para.runs = []
        level = normalizer._fallback_classify(para)
        assert level == 1


class TestDocxFormatNormalizerStrip:
    def test_fallback_strip_chinese_number(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("一、合同标的")
        assert result == "合同标的"

    def test_fallback_strip_sub_number(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("1、标的物名称")
        assert result == "标的物名称"

    def test_fallback_strip_paren_number(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("（一）合同标的")
        assert result == "合同标的"

    def test_fallback_strip_multi_level(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("1.2.3 具体条款")
        assert result == "具体条款"

    def test_fallback_strip_no_match(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("普通文本内容")
        assert result == "普通文本内容"

    def test_fallback_strip_empty(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        result = normalizer._fallback_strip("")
        assert result == ""


class TestDocxFormatNormalizerLevel:
    def test_get_level_with_llm_result(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        normalizer._llm_results = {0: {"level": 2, "prefix": "1."}}
        para = MagicMock()
        level = normalizer._get_level(para, 0)
        assert level == 2

    def test_get_level_without_llm_result(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = "普通文本"
        para.runs = []
        level = normalizer._get_level(para, 0)
        assert level == 1


class TestDocxFormatNormalizerClear:
    def test_clear_format(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        pPr = MagicMock()
        # Mock find to return elements for each tag
        pPr.find.return_value = MagicMock()
        normalizer._clear_format(pPr)
        # Should have tried to remove elements
        assert pPr.remove.call_count > 0


class TestDocxFormatNormalizerStripPrefix:
    def test_strip_prefix_no_match(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = "普通文本"
        para.runs = []
        normalizer._strip_prefix(para, 0)
        # Should not modify - no prefix match

    def test_strip_prefix_llm_prefix_no_match_in_text(self):
        normalizer = DocxFormatNormalizer(input_path="/tmp/test.docx")
        normalizer._llm_results = {0: {"prefix": "九、"}}
        para = MagicMock()
        para.text = "普通文本"
        para.runs = []
        normalizer._strip_prefix(para, 0)
        # Should not modify - prefix doesn't match text
