"""Tests for contract_review.services.extraction.heading_numbering."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.contract_review.services.extraction.heading_numbering import HeadingNumbering


class TestHeadingNumberingInit:
    def test_init_no_llm(self):
        hn = HeadingNumbering(llm_service=None)
        assert hn._llm is None

    def test_init_with_llm(self):
        mock_llm = MagicMock()
        hn = HeadingNumbering(llm_service=mock_llm)
        assert hn._llm == mock_llm


class TestHeadingNumberingApplyNumbering:
    def test_no_llm_skips(self):
        hn = HeadingNumbering(llm_service=None)
        doc = MagicMock()
        hn.apply_numbering(doc)  # Should not raise

    def test_no_headings_skips(self):
        mock_llm = MagicMock()
        hn = HeadingNumbering(llm_service=mock_llm)
        doc = MagicMock()
        doc.paragraphs = []
        with patch.object(hn, "_identify_headings_via_llm", return_value=[]):
            hn.apply_numbering(doc)  # Should not raise


class TestHeadingNumberingParseLlmResponse:
    def test_valid_json(self):
        text = '[{"index": 0, "level": 0}, {"index": 1, "level": 1}]'
        result = HeadingNumbering._parse_llm_response(text, 10)
        assert result == [(0, 0), (1, 1)]

    def test_json_in_codeblock(self):
        text = '```json\n[{"index": 2, "level": 0}]\n```'
        result = HeadingNumbering._parse_llm_response(text, 10)
        assert result == [(2, 0)]

    def test_invalid_json(self):
        result = HeadingNumbering._parse_llm_response("not json", 10)
        assert result == []

    def test_non_list(self):
        result = HeadingNumbering._parse_llm_response('{"key": "value"}', 10)
        assert result == []

    def test_out_of_range_index(self):
        text = '[{"index": 100, "level": 0}]'
        result = HeadingNumbering._parse_llm_response(text, 5)
        assert result == []

    def test_invalid_level(self):
        text = '[{"index": 0, "level": 5}]'
        result = HeadingNumbering._parse_llm_response(text, 5)
        assert result == []

    def test_negative_level_allowed(self):
        text = '[{"index": 0, "level": -1}]'
        result = HeadingNumbering._parse_llm_response(text, 5)
        assert result == [(0, -1)]

    def test_non_dict_items_skipped(self):
        text = '[{"index": 0, "level": 0}, "invalid", 42]'
        result = HeadingNumbering._parse_llm_response(text, 5)
        assert result == [(0, 0)]

    def test_non_int_values_skipped(self):
        text = '[{"index": "abc", "level": 0}]'
        result = HeadingNumbering._parse_llm_response(text, 5)
        assert result == []


class TestHeadingNumberingStripManualNumbers:
    def test_strip_chinese_numbering(self):
        doc = MagicMock()
        para = MagicMock()
        para.text = "一、产品名称"
        para.runs = [MagicMock(text="一、产品名称")]
        doc.paragraphs = [para]
        # Just ensure it doesn't raise
        HeadingNumbering._strip_manual_numbers(doc, [(0, 0)])

    def test_strip_decimal_numbering(self):
        doc = MagicMock()
        para = MagicMock()
        para.text = "1. 付款条款"
        para.runs = [MagicMock(text="1. 付款条款")]
        doc.paragraphs = [para]
        HeadingNumbering._strip_manual_numbers(doc, [(0, 0)])


class TestHeadingNumberingSupplementMissedHeadings:
    def test_empty_headings(self):
        doc = MagicMock()
        doc.paragraphs = []
        result = HeadingNumbering._supplement_missed_headings(doc, [])
        assert result == []


# Patch import for use in test methods
from unittest.mock import patch
