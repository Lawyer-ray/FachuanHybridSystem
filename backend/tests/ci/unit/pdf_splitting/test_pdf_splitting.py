"""PDF 拆分模块测试。"""

from __future__ import annotations

from apps.pdf_splitting.services.split.split_models import (
    PageDescriptor,
    SegmentDraft,
    OCRRuntimeProfile,
    OCRPageResult,
    _levenshtein_distance,
)
from apps.pdf_splitting.services.template_registry import (
    FILING_MATERIALS_V1,
    get_default_filename,
    get_segment_label,
    get_template_definition,
)
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector


class TestLevenshteinDistance:
    """Levenshtein 编辑距离测试。"""

    def test_identical_strings(self) -> None:
        assert _levenshtein_distance("abc", "abc") == 0

    def test_empty_strings(self) -> None:
        assert _levenshtein_distance("", "") == 0
        assert _levenshtein_distance("abc", "") == 3
        assert _levenshtein_distance("", "abc") == 3

    def test_single_edit(self) -> None:
        assert _levenshtein_distance("abc", "ab") == 1
        assert _levenshtein_distance("abc", "abcd") == 1
        assert _levenshtein_distance("abc", "adc") == 1

    def test_multiple_edits(self) -> None:
        assert _levenshtein_distance("kitten", "sitting") == 3

    def test_chinese_strings(self) -> None:
        assert _levenshtein_distance("民事起诉状", "民事起诉书") == 1


class TestSplitModels:
    """数据模型测试。"""

    def test_page_descriptor(self) -> None:
        desc = PageDescriptor(
            page_no=1,
            text="测试文本",
            normalized_text="测试文本",
            head_text="测试",
            source_method="ocr",
            ocr_failed=False,
            top_candidates=[],
        )
        assert desc.page_no == 1
        assert desc.text == "测试文本"

    def test_segment_draft(self) -> None:
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
        assert draft.page_start == 1
        assert draft.page_end == 5

    def test_ocr_runtime_profile(self) -> None:
        profile = OCRRuntimeProfile(key="test", use_v5=True, dpi=300, workers=4)
        assert profile.key == "test"
        assert profile.use_v5 is True

    def test_ocr_page_result(self) -> None:
        result = OCRPageResult(page_no=1, text="测试", source_method="ocr", ocr_failed=False)
        assert result.page_no == 1


class TestTemplateRegistry:
    """模板注册表测试。"""

    def test_get_template_definition_default(self) -> None:
        template = get_template_definition("nonexistent")
        assert template == FILING_MATERIALS_V1

    def test_get_template_definition_filing(self) -> None:
        template = get_template_definition("filing_materials_v1")
        assert template.key == "filing_materials_v1"
        assert len(template.rules) > 0

    def test_get_segment_label(self) -> None:
        label = get_segment_label("complaint")
        assert label == "起诉状"

    def test_get_segment_label_unrecognized(self) -> None:
        label = get_segment_label("unrecognized")
        assert label == "未识别材料"

    def test_get_default_filename(self) -> None:
        filename = get_default_filename("complaint")
        assert filename == "起诉状"

    def test_get_default_filename_unknown(self) -> None:
        filename = get_default_filename("unknown_type")
        assert filename == "未识别材料"

    def test_filing_materials_v1_rules(self) -> None:
        """验证立案材料模板包含所有必需规则。"""
        rules = FILING_MATERIALS_V1.rules
        segment_types = {r.segment_type for r in rules}
        assert "complaint" in segment_types
        assert "evidence_list" in segment_types
        assert "party_identity" in segment_types
        assert "authorization_materials" in segment_types

    def test_template_rule_has_keywords(self) -> None:
        """验证规则包含关键词。"""
        complaint_rule = next(r for r in FILING_MATERIALS_V1.rules if r.segment_type == "complaint")
        assert "起诉状" in complaint_rule.strong_keywords
        assert "诉讼请求" in complaint_rule.weak_keywords


class TestSegmentDetector:
    """SegmentDetector 测试。"""

    def setup_method(self) -> None:
        self.detector = SegmentDetector()

    def test_normalize_text(self) -> None:
        assert self.detector.normalize_text("  hello   world  ") == "helloworld"
        assert self.detector.normalize_text("") == ""
        assert self.detector.normalize_text(None) == ""

    def test_contains_keyword(self) -> None:
        assert self.detector.contains_keyword("民事起诉状内容", "起诉状") is True
        assert self.detector.contains_keyword("其他内容", "起诉状") is False

    def test_fuzzy_contains_keyword_exact(self) -> None:
        hit, decay = self.detector.fuzzy_contains_keyword("民事起诉状内容", "起诉状")
        assert hit is True
        assert decay == 1.0

    def test_fuzzy_contains_keyword_short_keyword(self) -> None:
        """短关键词（<=3字符）仅精确匹配。"""
        # "起诉" 是2个字符，<=3，所以只做精确匹配
        hit, _ = self.detector.fuzzy_contains_keyword("民事起诉书内容", "起诉书")
        assert hit is True

    def test_is_effective_text(self) -> None:
        assert self.detector.is_effective_text("这是一段足够长的文本内容用于测试") is True
        assert self.detector.is_effective_text("短") is False
        assert self.detector.is_effective_text("") is False

    def test_fill_unrecognized_gaps_no_gaps(self) -> None:
        """无间隙时原样返回。"""
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=5, segment_type="complaint",
                         filename="test.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=5)
        assert len(result) == 1

    def test_fill_unrecognized_gaps_with_gaps(self) -> None:
        """有间隙时填充未识别区间。"""
        segments = [
            SegmentDraft(order=1, page_start=3, page_end=5, segment_type="complaint",
                         filename="test.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
        ]
        result = self.detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(result) == 3  # gap + segment + gap
        assert result[0].segment_type == "unrecognized"
        assert result[0].page_start == 1
        assert result[0].page_end == 2
        assert result[2].segment_type == "unrecognized"
        assert result[2].page_start == 6
        assert result[2].page_end == 10

    def test_fill_unrecognized_gaps_empty(self) -> None:
        """空段落列表，全部为未识别。"""
        result = self.detector.fill_unrecognized_gaps(segments=[], total_pages=10)
        assert len(result) == 1
        assert result[0].segment_type == "unrecognized"
        assert result[0].page_start == 1
        assert result[0].page_end == 10

    def test_merge_adjacent_pack_segments(self) -> None:
        """合并相邻的同类型段落。"""
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=3, segment_type="party_identity",
                         filename="test1.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
            SegmentDraft(order=2, page_start=4, page_end=6, segment_type="party_identity",
                         filename="test2.pdf", confidence=0.7, source_method="rule", review_flag="normal"),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 1
        assert result[0].page_start == 1
        assert result[0].page_end == 6

    def test_merge_adjacent_different_types(self) -> None:
        """不同类型不合并。"""
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=3, segment_type="complaint",
                         filename="test1.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
            SegmentDraft(order=2, page_start=4, page_end=6, segment_type="evidence_list",
                         filename="test2.pdf", confidence=0.7, source_method="rule", review_flag="normal"),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 2

    def test_merge_adjacent_non_adjacent(self) -> None:
        """不相邻不合并。"""
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=3, segment_type="party_identity",
                         filename="test1.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
            SegmentDraft(order=2, page_start=5, page_end=7, segment_type="party_identity",
                         filename="test2.pdf", confidence=0.7, source_method="rule", review_flag="normal"),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 2
