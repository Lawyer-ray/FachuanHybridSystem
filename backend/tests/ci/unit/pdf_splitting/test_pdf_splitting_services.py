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
