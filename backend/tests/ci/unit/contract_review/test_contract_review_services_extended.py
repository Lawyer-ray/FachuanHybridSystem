"""Tests for contract_review format_normalizer - DocxFormatNormalizer."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestDocxFormatNormalizerInit:
    def test_default_output_path(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        input_path = tmp_path / "test.docx"
        input_path.touch()
        normalizer = DocxFormatNormalizer(input_path)
        assert normalizer.output_path == tmp_path / "test_规范化.docx"

    def test_custom_output_path(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        input_path = tmp_path / "input.docx"
        input_path.touch()
        output_path = tmp_path / "output.docx"
        normalizer = DocxFormatNormalizer(input_path, output_path=output_path)
        assert normalizer.output_path == output_path

    def test_reference_path_set(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        ref_path = tmp_path / "ref.docx"
        ref_path.touch()
        normalizer = DocxFormatNormalizer(tmp_path / "in.docx", reference_path=ref_path)
        assert normalizer.reference_path == ref_path


class TestDocxFormatNormalizerFallbackClassify:
    def _make_normalizer(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        p = tmp_path / "test.docx"
        p.touch()
        return DocxFormatNormalizer(p)

    def test_empty_text_returns_1(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.text = ""
        para.runs = []
        assert normalizer._fallback_classify(para) == 1

    def test_chinese_number_heading(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.text = "一、合同内容"
        para.runs = []
        assert normalizer._fallback_classify(para) == 0

    def test_parenthesized_chinese_number_heading(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.text = "（一）合同内容"
        para.runs = []
        assert normalizer._fallback_classify(para) == 0

    def test_digit_subitem(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.text = "1、第一条"
        para.runs = []
        assert normalizer._fallback_classify(para) == 2

    def test_default_body(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.text = "这是一段普通正文内容，没有特殊编号格式"
        para.runs = []
        assert normalizer._fallback_classify(para) == 1


class TestDocxFormatNormalizerFallbackStrip:
    def _make_normalizer(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        p = tmp_path / "test.docx"
        p.touch()
        return DocxFormatNormalizer(p)

    def test_strips_chinese_number(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("一、合同内容")
        assert result == "合同内容"

    def test_strips_digit_number(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("1、第一条约定")
        assert result == "第一条约定"

    def test_strips_parenthesized_number(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("（一）合同内容")
        assert result == "合同内容"

    def test_strips_dot_number(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("2. 付款方式")
        assert result == "付款方式"

    def test_no_stripping(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        text = "普通正文"
        result = normalizer._fallback_strip(text)
        assert result == text

    def test_multi_level_number(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("1.2.3 细则说明")
        assert result == "细则说明"

    def test_arabic_in_parens(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        result = normalizer._fallback_strip("（1）第一项")
        assert result == "第一项"


class TestDocxFormatNormalizerClearFormat:
    def _make_normalizer(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        p = tmp_path / "test.docx"
        p.touch()
        return DocxFormatNormalizer(p)

    def test_clears_old_format_elements(self, tmp_path):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        normalizer = self._make_normalizer(tmp_path)
        pPr = OxmlElement("w:pPr")
        for tag in ("w:spacing", "w:ind", "w:jc", "w:numPr"):
            pPr.append(OxmlElement(tag))
        normalizer._clear_format(pPr)
        for tag in ("w:spacing", "w:ind", "w:jc", "w:numPr"):
            assert pPr.find(qn(tag)) is None


class TestDocxFormatNormalizerGetLevel:
    def _make_normalizer(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        p = tmp_path / "test.docx"
        p.touch()
        return DocxFormatNormalizer(p)

    def test_uses_llm_result(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        normalizer._llm_results = {0: {"level": 0, "prefix": ""}}
        para = MagicMock()
        assert normalizer._get_level(para, 0) == 0

    def test_falls_back_to_rule(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = "一、合同内容"
        para.runs = []
        assert normalizer._get_level(para, 0) == 0


class TestDocxFormatNormalizerExtractRunFormat:
    def _make_normalizer(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer
        p = tmp_path / "test.docx"
        p.touch()
        return DocxFormatNormalizer(p)

    def test_no_runs_returns_empty(self, tmp_path):
        normalizer = self._make_normalizer(tmp_path)
        para = MagicMock()
        para.runs = []
        assert normalizer._extract_run_format(para) == {}
