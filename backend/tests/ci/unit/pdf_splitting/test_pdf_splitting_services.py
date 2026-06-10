"""
Tests for apps.pdf_splitting.services — PDF 分割服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ============================================================
# TemplateRegistry 测试
# ============================================================


class TestTemplateRegistry:
    """模板注册表测试"""

    def test_get_template_definition_known_key(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_template_definition

        template = get_template_definition("filing_materials_v1")
        assert template.key == "filing_materials_v1"
        assert len(template.rules) > 0

    def test_get_template_definition_unknown_defaults(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_template_definition

        template = get_template_definition("nonexistent")
        assert template.key == "filing_materials_v1"  # fallback

    def test_get_segment_label_known_type(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("complaint")
        assert label  # should return some label

    def test_get_segment_label_unknown(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("nonexistent_type_xyz")
        assert label == "nonexistent_type_xyz"

    def test_get_default_filename_known(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_default_filename

        filename = get_default_filename("complaint")
        assert filename  # should return something

    def test_get_default_filename_unknown(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_default_filename

        filename = get_default_filename("nonexistent")
        assert filename == "未识别材料"

    def test_filing_materials_rules_count(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        assert len(FILING_MATERIALS_V1.rules) == 7

    def test_segment_rule_has_keywords(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        complaint_rule = FILING_MATERIALS_V1.rules[0]
        assert complaint_rule.segment_type == "complaint"
        assert len(complaint_rule.strong_keywords) > 0
        assert "民事起诉状" in complaint_rule.strong_keywords

    def test_segment_rule_has_negative_keywords(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        complaint_rule = FILING_MATERIALS_V1.rules[0]
        assert len(complaint_rule.negative_keywords) > 0


# ============================================================
# SplitModels 测试
# ============================================================


class TestSplitModels:
    """PDF 分割数据模型测试"""

    def test_page_descriptor(self) -> None:
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        desc = PageDescriptor(
            page_no=1,
            text="起诉状内容",
            normalized_text="起诉状内容",
            head_text="起诉状",
            source_method="pdf_text",
            ocr_failed=False,
            top_candidates=[],
        )
        assert desc.page_no == 1
        assert desc.text == "起诉状内容"

    def test_segment_draft(self) -> None:
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        draft = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type="complaint",
            filename="起诉状.pdf",
            confidence=0.95,
            source_method="keyword",
            review_flag="ok",
        )
        assert draft.order == 1
        assert draft.page_start == 1
        assert draft.page_end == 5
        assert draft.confidence == 0.95

    def test_ocr_runtime_profile(self) -> None:
        from apps.pdf_splitting.services.split.split_models import OCRRuntimeProfile

        profile = OCRRuntimeProfile(key="test", use_v5=True, dpi=300, workers=4)
        assert profile.key == "test"
        assert profile.use_v5 is True

    def test_ocr_page_result(self) -> None:
        from apps.pdf_splitting.services.split.split_models import OCRPageResult

        result = OCRPageResult(page_no=1, text="OCR text", source_method="ocr", ocr_failed=False)
        assert result.page_no == 1
        assert result.ocr_failed is False

    def test_levenshtein_distance(self) -> None:
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("kitten", "sitting") == 3
        assert _levenshtein_distance("", "abc") == 3
        assert _levenshtein_distance("abc", "abc") == 0
        assert _levenshtein_distance("abc", "") == 3


# ============================================================
# SegmentTemplateRule frozen dataclass 测试
# ============================================================


class TestSegmentTemplateRule:
    """SegmentTemplateRule 测试"""

    def test_rule_basic(self) -> None:
        from apps.pdf_splitting.services.template_registry import SegmentTemplateRule

        rule = SegmentTemplateRule(
            segment_type="test",
            label="Test",
            default_filename="test.pdf",
            strong_keywords=("keyword1",),
        )
        assert rule.segment_type == "test"
        assert rule.weak_keywords == ()
        assert rule.negative_keywords == ()

    def test_rule_frozen(self) -> None:
        from apps.pdf_splitting.services.template_registry import SegmentTemplateRule

        rule = SegmentTemplateRule(
            segment_type="test",
            label="Test",
            default_filename="test.pdf",
            strong_keywords=("kw",),
        )
        with pytest.raises(AttributeError):
            rule.segment_type = "changed"


# ---------------------------------------------------------------------------
# SegmentDetector extended tests
# ---------------------------------------------------------------------------

class TestSegmentDetectorExtended:
    def _make_detector(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        return SegmentDetector()

    def test_normalize_text(self):
        detector = self._make_detector()
        result = detector.normalize_text("  hello  world  ")
        assert result == "helloworld" or "hello" in result

    def test_contains_keyword(self):
        detector = self._make_detector()
        assert detector.contains_keyword("这是一份起诉状", "起诉状") is True
        assert detector.contains_keyword("普通文本", "起诉状") is False

    def test_fuzzy_contains_keyword_exact(self):
        detector = self._make_detector()
        hit, decay = detector.fuzzy_contains_keyword("起诉状内容", "起诉状")
        assert hit is True
        assert decay == 1.0

    def test_fuzzy_contains_keyword_short_no_fuzzy(self):
        detector = self._make_detector()
        # Short keywords (<=3 chars) only do exact match
        hit, decay = detector.fuzzy_contains_keyword("起诉", "起诉")
        assert hit is True  # exact match works

    def test_is_effective_text_true(self):
        detector = self._make_detector()
        assert detector.is_effective_text("这是一段足够长的文本内容") is True

    def test_is_effective_text_false(self):
        detector = self._make_detector()
        assert detector.is_effective_text("短") is False

    def test_fill_unrecognized_gaps(self):
        from apps.pdf_splitting.services.split.split_models import SegmentDraft
        from apps.pdf_splitting.models import PdfSplitSegmentType, PdfSplitReviewFlag
        detector = self._make_detector()
        segments = [
            SegmentDraft(
                order=1, page_start=3, page_end=5,
                segment_type=PdfSplitSegmentType.COMPLAINT,
                filename="test.pdf", confidence=0.8,
                source_method="rule", review_flag=PdfSplitReviewFlag.NORMAL,
            )
        ]
        filled = detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(filled) == 3  # gap before + segment + gap after
        assert filled[0].page_start == 1
        assert filled[0].page_end == 2
        assert filled[-1].page_start == 6
        assert filled[-1].page_end == 10

    def test_merge_adjacent_pack_segments(self):
        from apps.pdf_splitting.services.split.split_models import SegmentDraft
        from apps.pdf_splitting.models import PdfSplitSegmentType, PdfSplitReviewFlag
        detector = self._make_detector()
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=2, segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                         filename="a.pdf", confidence=0.8, source_method="rule", review_flag=PdfSplitReviewFlag.NORMAL),
            SegmentDraft(order=2, page_start=3, page_end=4, segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                         filename="b.pdf", confidence=0.9, source_method="rule", review_flag=PdfSplitReviewFlag.NORMAL),
        ]
        merged = detector._merge_adjacent_pack_segments(segments)
        assert len(merged) == 1
        assert merged[0].page_start == 1
        assert merged[0].page_end == 4

    def test_merge_different_types_no_merge(self):
        from apps.pdf_splitting.services.split.split_models import SegmentDraft
        from apps.pdf_splitting.models import PdfSplitSegmentType, PdfSplitReviewFlag
        detector = self._make_detector()
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=2, segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                         filename="a.pdf", confidence=0.8, source_method="rule", review_flag=PdfSplitReviewFlag.NORMAL),
            SegmentDraft(order=2, page_start=3, page_end=4, segment_type=PdfSplitSegmentType.COMPLAINT,
                         filename="b.pdf", confidence=0.9, source_method="rule", review_flag=PdfSplitReviewFlag.NORMAL),
        ]
        merged = detector._merge_adjacent_pack_segments(segments)
        assert len(merged) == 2


class TestPdfSplitJobServiceNormalize:
    def _make_service(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService
        return PdfSplitJobService()

    def test_normalize_split_mode_valid(self):
        svc = self._make_service()
        assert svc._normalize_split_mode("content_analysis") == "content_analysis"

    def test_normalize_split_mode_invalid(self):
        svc = self._make_service()
        assert svc._normalize_split_mode("invalid") == "content_analysis"

    def test_normalize_split_mode_none(self):
        svc = self._make_service()
        assert svc._normalize_split_mode(None) == "content_analysis"

    def test_normalize_ocr_profile_valid(self):
        svc = self._make_service()
        assert svc._normalize_ocr_profile("balanced") == "balanced"

    def test_normalize_ocr_profile_invalid(self):
        svc = self._make_service()
        assert svc._normalize_ocr_profile("invalid") == "balanced"

    def test_is_absolute_path_unix(self):
        svc = self._make_service()
        assert svc._is_absolute_path("/tmp/test.pdf") is True
        assert svc._is_absolute_path("relative/test.pdf") is False
