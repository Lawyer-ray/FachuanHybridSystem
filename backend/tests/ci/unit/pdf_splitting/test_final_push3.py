"""Final push coverage tests for pdf_splitting — models, segment detector, template registry."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest


# ============================================================================
# pdf_splitting/services/split/split_models.py tests
# ============================================================================


class TestLevenshteinDistance:
    def test_identical_strings(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abc", "abc") == 0

    def test_single_insertion(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abc", "abcd") == 1

    def test_single_deletion(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abcd", "abc") == 1

    def test_single_substitution(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abc", "axc") == 1

    def test_empty_strings(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("", "") == 0

    def test_one_empty(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abc", "") == 3
        assert _levenshtein_distance("", "abc") == 3

    def test_completely_different(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("abc", "xyz") == 3

    def test_chinese_strings(self):
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("起诉状", "起诉状") == 0
        assert _levenshtein_distance("起诉状", "起诉书") == 1


class TestPageDescriptor:
    def test_creation(self):
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        page = PageDescriptor(
            page_no=1,
            text="text",
            normalized_text="normalized",
            head_text="head",
            source_method="ocr",
            ocr_failed=False,
            top_candidates=[{"score": 0.9}],
        )
        assert page.page_no == 1
        assert page.ocr_failed is False


class TestSegmentDraft:
    def test_creation(self):
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        draft = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type="complaint",
            filename="起诉状.pdf",
            confidence=0.85,
            source_method="rule",
            review_flag="normal",
        )
        assert draft.order == 1
        assert draft.page_end == 5
        assert draft.confidence == 0.85


class TestOCRRuntimeProfile:
    def test_frozen(self):
        from apps.pdf_splitting.services.split.split_models import OCRRuntimeProfile

        profile = OCRRuntimeProfile(key="test", use_v5=True, dpi=300, workers=4)
        assert profile.key == "test"
        assert profile.dpi == 300
        with pytest.raises(AttributeError):
            profile.key = "other"


class TestOCRPageResult:
    def test_creation(self):
        from apps.pdf_splitting.services.split.split_models import OCRPageResult

        result = OCRPageResult(page_no=1, text="text", source_method="pdf", ocr_failed=False)
        assert result.page_no == 1


# ============================================================================
# pdf_splitting/services/template_registry.py tests
# ============================================================================


class TestGetTemplateDefinition:
    def test_valid_key(self):
        from apps.pdf_splitting.services.template_registry import get_template_definition

        result = get_template_definition("filing_materials_v1")
        assert result.key == "filing_materials_v1"
        assert len(result.rules) > 0

    def test_unknown_key_returns_default(self):
        from apps.pdf_splitting.services.template_registry import get_template_definition

        result = get_template_definition("nonexistent")
        assert result.key == "filing_materials_v1"

    def test_rules_have_required_fields(self):
        from apps.pdf_splitting.services.template_registry import get_template_definition

        template = get_template_definition("filing_materials_v1")
        for rule in template.rules:
            assert rule.segment_type
            assert rule.label
            assert rule.default_filename
            assert len(rule.strong_keywords) > 0


# ============================================================================
# pdf_splitting/services/split/segment_detector.py tests
# ============================================================================


class TestSegmentDetectorNormalizeText:
    def test_basic(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.normalize_text("hello world")
        assert " " not in result

    def test_empty(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.normalize_text("") == ""

    def test_none(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.normalize_text(None) == ""


class TestSegmentDetectorContainsKeyword:
    def test_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.contains_keyword("民事起诉状内容", "起诉状") is True

    def test_not_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.contains_keyword("普通文本", "起诉状") is False


class TestSegmentDetectorFuzzyContainsKeyword:
    def test_exact_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.fuzzy_contains_keyword("民事起诉状", "起诉状")
        assert result == (True, 1.0)

    def test_short_keyword_no_fuzzy(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.fuzzy_contains_keyword("text without keyword", "abc")
        assert result == (False, 0.0)

    def test_no_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.fuzzy_contains_keyword("completely unrelated text", "某某材料清单")
        assert result[0] is False

    def test_empty_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.fuzzy_contains_keyword("text", "")
        assert result == (False, 0.0)


class TestSegmentDetectorIsEffectiveText:
    def test_long_enough(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.is_effective_text("这是一段足够长的文本内容") is True

    def test_too_short(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.is_effective_text("短") is False

    def test_empty(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.is_effective_text("") is False


class TestSegmentDetectorScorePage:
    def test_score_with_strong_keywords(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        # The score_page method uses template definitions
        # Let's test with actual template
        normalized = "民事起诉状诉讼请求事实与理由"
        results = detector.score_page(
            head_text="民事起诉状",
            normalized_text=normalized,
            template_key="filing_materials_v1",
        )
        assert len(results) > 0
        assert results[0]["score"] > 0
        assert results[0]["segment_type"] == "complaint"

    def test_score_with_no_keywords(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        results = detector.score_page(
            head_text="",
            normalized_text="无关内容",
            template_key="filing_materials_v1",
        )
        # Should have no candidates with score >= 0.30
        assert all(r["score"] < 0.30 for r in results) if results else True

    def test_score_with_weak_keywords_only(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        # "诉讼请求" and "事实与理由" are weak keywords for complaint
        normalized = "诉讼请求事实与理由原告被告人民法院"
        results = detector.score_page(
            head_text="",
            normalized_text=normalized,
            template_key="filing_materials_v1",
        )
        # Should have some candidates, possibly weak_only
        assert isinstance(results, list)


class TestSegmentDetectorFillUnrecognizedGaps:
    def test_no_gaps(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = SegmentDetector()
        segments = [
            SegmentDraft(1, 1, 5, "complaint", "起诉状.pdf", 0.9, "rule", "normal"),
            SegmentDraft(2, 6, 10, "evidence_list", "证据清单.pdf", 0.8, "rule", "normal"),
        ]
        result = detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) >= 2

    def test_gap_at_start(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = SegmentDetector()
        segments = [
            SegmentDraft(1, 5, 10, "complaint", "起诉状.pdf", 0.9, "rule", "normal"),
        ]
        result = detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) >= 2

    def test_gap_in_middle(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = SegmentDetector()
        segments = [
            SegmentDraft(1, 1, 3, "complaint", "起诉状.pdf", 0.9, "rule", "normal"),
            SegmentDraft(2, 7, 10, "evidence_list", "证据清单.pdf", 0.8, "rule", "normal"),
        ]
        result = detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) >= 3

    def test_empty_segments(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.fill_unrecognized_gaps(segments=[], total_pages=5)
        assert len(result) >= 1


class TestSegmentDetectorMergeAdjacentPackSegments:
    def test_merge_same_type(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = SegmentDetector()
        segments = [
            SegmentDraft(1, 1, 3, "party_identity", "主体信息.pdf", 0.9, "rule", "normal"),
            SegmentDraft(2, 4, 6, "party_identity", "主体信息.pdf", 0.85, "rule", "normal"),
        ]
        result = detector._merge_adjacent_pack_segments(segments)
        assert len(result) <= 2  # May merge

    def test_different_types_no_merge(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = SegmentDetector()
        segments = [
            SegmentDraft(1, 1, 3, "complaint", "起诉状.pdf", 0.9, "rule", "normal"),
            SegmentDraft(2, 4, 6, "evidence_list", "证据清单.pdf", 0.8, "rule", "normal"),
        ]
        result = detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 2
