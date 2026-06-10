"""Batch 6 coverage tests for document_recognition module."""

from __future__ import annotations

import pytest


class TestCaseNumberMixin:
    def _make_mixin(self):
        from apps.document_recognition.services._case_number_mixin import CaseNumberMixin
        return CaseNumberMixin()

    def test_extract_case_number_chinese_bracket(self):
        mixin = self._make_mixin()
        text = "（2023）京0108民初12345号"
        result = mixin._extract_case_number_by_regex(text)
        assert result is not None
        assert "2023" in result

    def test_extract_case_number_english_bracket(self):
        mixin = self._make_mixin()
        text = "(2023)京0108民初12345号"
        result = mixin._extract_case_number_by_regex(text)
        assert result is not None
        assert "2023" in result

    def test_extract_case_number_none_text(self):
        mixin = self._make_mixin()
        assert mixin._extract_case_number_by_regex(None) is None

    def test_extract_case_number_empty_text(self):
        mixin = self._make_mixin()
        assert mixin._extract_case_number_by_regex("") is None

    def test_extract_case_number_no_match(self):
        mixin = self._make_mixin()
        assert mixin._extract_case_number_by_regex("没有案号的文本") is None

    def test_normalize_case_number(self):
        mixin = self._make_mixin()
        result = mixin._normalize_case_number("（2023）京0108民初12345号")
        assert result == "（2023）京0108民初12345号"

    def test_normalize_case_number_empty(self):
        mixin = self._make_mixin()
        assert mixin._normalize_case_number("") == ""

    def test_normalize_case_number_english_to_chinese(self):
        mixin = self._make_mixin()
        result = mixin._normalize_case_number("(2023)京0108民初12345号")
        assert "（" in result
        assert "）" in result

    def test_normalize_case_number_no_bracket(self):
        mixin = self._make_mixin()
        result = mixin._normalize_case_number("2023京0108民初12345号")
        assert "（" in result
