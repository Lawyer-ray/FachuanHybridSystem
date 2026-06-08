"""Coverage tests for contract_review format normalizer."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestDocxFormatNormalizer:
    def test_init_defaults(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        input_path = tmp_path / "test.docx"
        input_path.touch()
        normalizer = DocxFormatNormalizer(input_path=input_path)
        assert normalizer.input_path == input_path
        assert normalizer.reference_path is None
        assert normalizer.doc is None
        assert normalizer._llm_results == {}

    def test_init_with_reference(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        input_path = tmp_path / "test.docx"
        ref_path = tmp_path / "ref.docx"
        input_path.touch()
        ref_path.touch()
        normalizer = DocxFormatNormalizer(input_path=input_path, reference_path=ref_path)
        assert normalizer.reference_path == ref_path

    def test_init_custom_output(self, tmp_path):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        input_path = tmp_path / "test.docx"
        output_path = tmp_path / "out.docx"
        input_path.touch()
        normalizer = DocxFormatNormalizer(input_path=input_path, output_path=output_path)
        assert normalizer.output_path == output_path

    def test_fallback_classify_empty(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = ""
        para.runs = []
        assert normalizer._fallback_classify(para) == 1

    def test_fallback_classify_chinese_number(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = "一、合同条款"
        para.runs = []
        assert normalizer._fallback_classify(para) == 0

    def test_fallback_classify_sub_item(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        normalizer._llm_results = {}
        para = MagicMock()
        para.text = "1、具体内容"
        para.runs = []
        assert normalizer._fallback_classify(para) == 2

    def test_fallback_strip_chinese_number(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        result = normalizer._fallback_strip("一、合同条款")
        assert "合同条款" in result
        assert "一、" not in result

    def test_fallback_strip_sub_number(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        result = normalizer._fallback_strip("1. 具体内容")
        assert "具体内容" in result

    def test_fallback_strip_no_match(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        result = normalizer._fallback_strip("普通段落文字")
        assert result == "普通段落文字"

    def test_get_level_from_llm_results(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        normalizer._llm_results = {0: {"level": 0, "prefix": ""}}
        para = MagicMock()
        assert normalizer._get_level(para, 0) == 0

    def test_clear_format(self):
        from apps.contract_review.services.format_normalizer.docx_format_normalizer import DocxFormatNormalizer

        normalizer = DocxFormatNormalizer.__new__(DocxFormatNormalizer)
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        pPr = OxmlElement("w:pPr")
        for tag in ("w:spacing", "w:ind", "w:jc", "w:numPr"):
            pPr.append(OxmlElement(tag))
        normalizer._clear_format(pPr)
        assert len(list(pPr)) == 0
