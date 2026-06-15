"""Tests for template_registry and segment_detector continuation logic."""

from __future__ import annotations

import pytest

from apps.pdf_splitting.models import PdfSplitSegmentType
from apps.pdf_splitting.services.template_registry import (
    SegmentTemplateRule,
    TemplateDefinition,
    get_template_definition,
    get_segment_label,
    get_default_filename,
)
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector


# ---------------------------------------------------------------------------
# template_registry
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_get_template_definition_known(self):
        td = get_template_definition("filing_materials_v1")
        assert td.key == "filing_materials_v1"
        assert len(td.rules) > 0

    def test_get_template_definition_unknown_returns_default(self):
        td = get_template_definition("nonexistent")
        assert td.key == "filing_materials_v1"

    def test_get_segment_label_known(self):
        label = get_segment_label(PdfSplitSegmentType.COMPLAINT)
        assert label == "起诉状"

    def test_get_segment_label_unrecognized(self):
        label = get_segment_label(PdfSplitSegmentType.UNRECOGNIZED)
        assert label == "未识别材料"

    def test_get_segment_label_unknown_returns_type(self):
        label = get_segment_label("nonexistent_type")
        assert label == "nonexistent_type"

    def test_get_default_filename_known(self):
        fn = get_default_filename(PdfSplitSegmentType.COMPLAINT)
        assert fn == "起诉状"

    def test_get_default_filename_unknown(self):
        fn = get_default_filename("nonexistent")
        assert fn == "未识别材料"


# ---------------------------------------------------------------------------
# SegmentDetector — continuation and scoring
# ---------------------------------------------------------------------------


class TestSegmentDetectorFillUnrecognizedGaps:
    def test_empty_drafts_fills_all_pages(self):
        sd = SegmentDetector()
        result = sd.fill_unrecognized_gaps(segments=[], total_pages=10)
        assert len(result) == 1
        assert result[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert result[0].page_start == 1
        assert result[0].page_end == 10


class TestSegmentDetectorMergeAdjacentPackSegments:
    def test_empty(self):
        sd = SegmentDetector()
        result = sd._merge_adjacent_pack_segments([])
        assert result == []

    def test_non_adjacent(self):
        sd = SegmentDetector()
        from apps.pdf_splitting.services.split.split_models import SegmentDraft
        from apps.pdf_splitting.models import PdfSplitSegmentType

        d1 = SegmentDraft(order=0, page_start=1, page_end=2, segment_type=PdfSplitSegmentType.PARTY_IDENTITY, filename="a.pdf", confidence=0.9, source_method="pdf", review_flag="auto")
        d2 = SegmentDraft(order=1, page_start=5, page_end=6, segment_type=PdfSplitSegmentType.PARTY_IDENTITY, filename="b.pdf", confidence=0.9, source_method="pdf", review_flag="auto")
        result = sd._merge_adjacent_pack_segments([d1, d2])
        assert len(result) == 2

    def test_adjacent_same_type(self):
        sd = SegmentDetector()
        from apps.pdf_splitting.services.split.split_models import SegmentDraft
        from apps.pdf_splitting.models import PdfSplitSegmentType

        d1 = SegmentDraft(order=0, page_start=1, page_end=2, segment_type=PdfSplitSegmentType.PARTY_IDENTITY, filename="a.pdf", confidence=0.9, source_method="pdf", review_flag="auto")
        d2 = SegmentDraft(order=1, page_start=3, page_end=5, segment_type=PdfSplitSegmentType.PARTY_IDENTITY, filename="b.pdf", confidence=0.9, source_method="pdf", review_flag="auto")
        result = sd._merge_adjacent_pack_segments([d1, d2])
        assert len(result) == 1
        assert result[0].page_start == 1
        assert result[0].page_end == 5


# ---------------------------------------------------------------------------
# SegmentDetector — complain-specific logic
# ---------------------------------------------------------------------------


class TestSegmentDetectorComplaintTerminalKeywords:
    def test_has_terminal_keyword(self):
        sd = SegmentDetector()
        # "此致" is a terminal keyword
        assert sd.COMPLAINT_TERMINAL_KEYWORDS == ("此致", "具状人", "起诉人", "起诉状具状人", "日期")

    def test_complaint_attachment_keywords(self):
        sd = SegmentDetector()
        assert "证据" in sd.COMPLAINT_ATTACHMENT_KEYWORDS
        assert "授权委托书" in sd.COMPLAINT_ATTACHMENT_KEYWORDS

    def test_complaint_max_span(self):
        sd = SegmentDetector()
        assert sd.COMPLAINT_MAX_SPAN == 20
