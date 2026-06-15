"""Tests for split_models (levenshtein, dataclasses) and segment_detector helpers."""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split.split_models import (
    _levenshtein_distance,
    PageDescriptor,
    SegmentDraft,
    OCRRuntimeProfile,
    OCRPageResult,
)


# ---------------------------------------------------------------------------
# _levenshtein_distance
# ---------------------------------------------------------------------------


class TestLevenshteinDistance:
    def test_identical(self):
        assert _levenshtein_distance("abc", "abc") == 0

    def test_empty_vs_empty(self):
        assert _levenshtein_distance("", "") == 0

    def test_empty_vs_string(self):
        assert _levenshtein_distance("", "abc") == 3

    def test_single_substitution(self):
        assert _levenshtein_distance("abc", "axc") == 1

    def test_insertion(self):
        assert _levenshtein_distance("ac", "abc") == 1

    def test_deletion(self):
        assert _levenshtein_distance("abc", "ac") == 1

    def test_completely_different(self):
        assert _levenshtein_distance("abc", "xyz") == 3

    def test_longer_first(self):
        assert _levenshtein_distance("kitten", "sitting") == 3

    def test_single_char(self):
        assert _levenshtein_distance("a", "") == 1
        assert _levenshtein_distance("", "a") == 1


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_page_descriptor(self):
        pd = PageDescriptor(
            page_no=1,
            text="hello",
            normalized_text="hello",
            head_text="he",
            source_method="pdf",
            ocr_failed=False,
            top_candidates=[],
        )
        assert pd.page_no == 1

    def test_segment_draft(self):
        sd = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type="complaint",
            filename="test.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
        assert sd.confidence == 0.9

    def test_ocr_runtime_profile(self):
        profile = OCRRuntimeProfile(key="default", use_v5=True, dpi=300, workers=4)
        assert profile.dpi == 300

    def test_ocr_page_result(self):
        result = OCRPageResult(page_no=1, text="text", source_method="pdf", ocr_failed=False)
        assert result.ocr_failed is False


# ---------------------------------------------------------------------------
# SegmentDetector — pure methods
# ---------------------------------------------------------------------------


class TestSegmentDetectorNormalizeText:
    def test_basic(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.normalize_text("hello world") == "helloworld"

    def test_empty(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.normalize_text("") == ""


class TestSegmentDetectorContainsKeyword:
    def test_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.contains_keyword("this is a test", "test") is True

    def test_not_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.contains_keyword("this is a test", "missing") is False


class TestSegmentDetectorIsEffectiveText:
    def test_short(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.is_effective_text("short") is False

    def test_long(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        assert sd.is_effective_text("this is a long enough text") is True


class TestSegmentDetectorFuzzyContainsKeyword:
    def test_exact_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("this is a test", "test")
        assert found is True
        assert coeff == 1.0

    def test_no_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello world", "xyz")
        assert found is False
        assert coeff == 0.0

    def test_empty_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello", "")
        assert found is False
        assert coeff == 0.0

    def test_short_keyword_no_fuzzy(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello", "xyz")
        assert found is False

    def test_fuzzy_match_medium_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        # keyword "测试文本" (len 4) -> max_dist=1, "测试文" (len 3) is within edit distance 1
        found, coeff = sd.fuzzy_contains_keyword("这是测试文本的内容", "测试文本")
        assert found is True
        assert coeff == 1.0  # exact match via normalization

    def test_fuzzy_match_long_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        sd = SegmentDetector()
        # keyword "证据清单" (len 8 normalized) -> max_dist=2
        found, coeff = sd.fuzzy_contains_keyword("提交了证据清单明细", "证据清单")
        assert found is True
        assert coeff == 1.0
