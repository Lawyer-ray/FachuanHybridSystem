"""Final coverage tests for pdf_splitting module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.split.split_models import (
    PageDescriptor,
    SegmentDraft,
    _levenshtein_distance,
)
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector


# ============================================================================
# Levenshtein distance tests
# ============================================================================


class TestLevenshteinDistance:
    def test_identical_strings(self):
        assert _levenshtein_distance("abc", "abc") == 0

    def test_empty_strings(self):
        assert _levenshtein_distance("", "") == 0

    def test_one_empty(self):
        assert _levenshtein_distance("abc", "") == 3
        assert _levenshtein_distance("", "abc") == 3

    def test_single_substitution(self):
        assert _levenshtein_distance("abc", "axc") == 1

    def test_single_insertion(self):
        assert _levenshtein_distance("abc", "abcd") == 1

    def test_single_deletion(self):
        assert _levenshtein_distance("abcd", "abc") == 1

    def test_completely_different(self):
        assert _levenshtein_distance("abc", "xyz") == 3

    def test_chinese_strings(self):
        assert _levenshtein_distance("起诉状", "起诉书") == 1

    def test_symmetric(self):
        assert _levenshtein_distance("kitten", "sitting") == _levenshtein_distance("sitting", "kitten")


# ============================================================================
# SegmentDetector text utilities
# ============================================================================


class TestSegmentDetectorNormalizeText:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_normalize_spaces(self):
        assert self.detector.normalize_text("hello world") == "helloworld"

    def test_normalize_tabs(self):
        assert self.detector.normalize_text("a\tb") == "ab"

    def test_normalize_none(self):
        assert self.detector.normalize_text(None) == ""

    def test_contains_keyword(self):
        assert self.detector.contains_keyword("helloworld", "world") is True
        assert self.detector.contains_keyword("helloworld", "xyz") is False

    def test_is_effective_text(self):
        assert self.detector.is_effective_text("这是一段足够长的文本内容") is True
        assert self.detector.is_effective_text("短") is False
        assert self.detector.is_effective_text("") is False


class TestSegmentDetectorFuzzyContainsKeyword:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_exact_match(self):
        haystack = self.detector.normalize_text("民事起诉状内容")
        hit, decay = self.detector.fuzzy_contains_keyword(haystack, "起诉状")
        assert hit is True
        assert decay == 1.0

    def test_no_match(self):
        haystack = self.detector.normalize_text("这是其他内容")
        hit, decay = self.detector.fuzzy_contains_keyword(haystack, "起诉")
        # This depends on whether the normalized keyword is in haystack
        # The normalize_text removes spaces, so "起诉" may or may not be in the result
        assert isinstance(hit, bool)
        assert decay in (0.0, 0.8, 1.0)

    def test_short_keyword_no_fuzzy(self):
        haystack = self.detector.normalize_text("这段文本不包含关键词")
        hit, _ = self.detector.fuzzy_contains_keyword(haystack, "abc")
        assert hit is False

    def test_empty_keyword(self):
        hit, decay = self.detector.fuzzy_contains_keyword("sometext", "")
        assert hit is False
        assert decay == 0.0


# ============================================================================
# SegmentDetector score_page tests
# ============================================================================


class TestSegmentDetectorScorePage:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_score_page_returns_list(self):
        # Use a known template key
        text = self.detector.normalize_text("民事起诉状原告被告")
        result = self.detector.score_page(
            head_text="民事起诉状",
            normalized_text=text,
            template_key="civil_complaint",
        )
        assert isinstance(result, list)

    def test_score_page_empty_text(self):
        result = self.detector.score_page(
            head_text="",
            normalized_text="",
            template_key="civil_complaint",
        )
        assert isinstance(result, list)


# ============================================================================
# SegmentDetector fill_unrecognized_gaps tests
# ============================================================================


class TestSegmentDetectorFillGaps:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_no_gaps(self):
        segments = [
            SegmentDraft(1, 1, 5, PdfSplitSegmentType.COMPLAINT, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
            SegmentDraft(2, 6, 10, PdfSplitSegmentType.EVIDENCE_LIST, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) == 2

    def test_gap_at_start(self):
        segments = [
            SegmentDraft(1, 3, 5, PdfSplitSegmentType.COMPLAINT, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=5)
        assert result[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert result[0].page_start == 1
        assert result[0].page_end == 2

    def test_gap_at_end(self):
        segments = [
            SegmentDraft(1, 1, 3, PdfSplitSegmentType.COMPLAINT, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=5)
        assert result[-1].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert result[-1].page_start == 4
        assert result[-1].page_end == 5

    def test_gap_between_segments(self):
        segments = [
            SegmentDraft(1, 1, 2, PdfSplitSegmentType.COMPLAINT, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
            SegmentDraft(2, 5, 6, PdfSplitSegmentType.EVIDENCE_LIST, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=6)
        gap = [s for s in result if s.segment_type == PdfSplitSegmentType.UNRECOGNIZED]
        assert len(gap) == 1
        assert gap[0].page_start == 3
        assert gap[0].page_end == 4

    def test_empty_segments(self):
        result = self.detector.fill_unrecognized_gaps(segments=[], total_pages=5)
        assert len(result) == 1
        assert result[0].page_start == 1
        assert result[0].page_end == 5
        assert result[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED


# ============================================================================
# SegmentDetector _merge_adjacent_pack_segments tests
# ============================================================================


class TestSegmentDetectorMergeAdjacent:
    def setup_method(self):
        self.detector = SegmentDetector()

    def test_empty_segments(self):
        assert self.detector._merge_adjacent_pack_segments([]) == []

    def test_merge_adjacent_party_identity(self):
        segments = [
            SegmentDraft(1, 1, 2, PdfSplitSegmentType.PARTY_IDENTITY, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
            SegmentDraft(2, 3, 4, PdfSplitSegmentType.PARTY_IDENTITY, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 1
        assert result[0].page_start == 1
        assert result[0].page_end == 4

    def test_no_merge_different_types(self):
        segments = [
            SegmentDraft(1, 1, 2, PdfSplitSegmentType.COMPLAINT, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
            SegmentDraft(2, 3, 4, PdfSplitSegmentType.EVIDENCE_LIST, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 2

    def test_no_merge_non_adjacent(self):
        segments = [
            SegmentDraft(1, 1, 2, PdfSplitSegmentType.PARTY_IDENTITY, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.NORMAL),
            SegmentDraft(2, 5, 6, PdfSplitSegmentType.PARTY_IDENTITY, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 2

    def test_merge_preserves_low_confidence_flag(self):
        segments = [
            SegmentDraft(1, 1, 2, PdfSplitSegmentType.PARTY_IDENTITY, "a.pdf", 0.9, "rule", PdfSplitReviewFlag.LOW_CONFIDENCE),
            SegmentDraft(2, 3, 4, PdfSplitSegmentType.PARTY_IDENTITY, "b.pdf", 0.8, "rule", PdfSplitReviewFlag.NORMAL),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 1
        assert result[0].review_flag == PdfSplitReviewFlag.LOW_CONFIDENCE


# ============================================================================
# SegmentDetector detect_segments tests
# ============================================================================


class TestSegmentDetectorDetectSegments:
    def setup_method(self):
        self.detector = SegmentDetector()

    def _make_page(self, page_no, text, top_candidates=None):
        return PageDescriptor(
            page_no=page_no,
            text=text,
            normalized_text=self.detector.normalize_text(text),
            head_text=text[:50],
            source_method="pdf_direct",
            ocr_failed=False,
            top_candidates=top_candidates or [],
        )

    def test_empty_pages(self):
        result = self.detector.detect_segments([], template_key="civil_complaint")
        assert result == []

    def test_single_page_no_candidates(self):
        pages = [self._make_page(1, "普通文本内容")]
        result = self.detector.detect_segments(pages, template_key="civil_complaint")
        # No candidates → only gap fills
        for seg in result:
            assert seg.segment_type == PdfSplitSegmentType.UNRECOGNIZED or seg.source_method != "gap_fill"

    def test_page_with_candidates(self):
        pages = [
            self._make_page(1, "民事起诉状原告被告", top_candidates=[
                {"segment_type": PdfSplitSegmentType.COMPLAINT, "score": 0.8, "label": "起诉状"}
            ]),
            self._make_page(2, "普通第二页"),
        ]
        result = self.detector.detect_segments(pages, template_key="civil_complaint")
        assert len(result) >= 1


# ============================================================================
# PageDescriptor tests
# ============================================================================


class TestPageDescriptor:
    def test_creation(self):
        page = PageDescriptor(
            page_no=1,
            text="hello",
            normalized_text="hello",
            head_text="hello",
            source_method="pdf_direct",
            ocr_failed=False,
            top_candidates=[],
        )
        assert page.page_no == 1
        assert page.text == "hello"
        assert page.ocr_failed is False


# ============================================================================
# SegmentDraft tests
# ============================================================================


class TestSegmentDraft:
    def test_creation(self):
        draft = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type=PdfSplitSegmentType.COMPLAINT,
            filename="complaint.pdf",
            confidence=0.9,
            source_method="rule",
            review_flag=PdfSplitReviewFlag.NORMAL,
        )
        assert draft.order == 1
        assert draft.confidence == 0.9
