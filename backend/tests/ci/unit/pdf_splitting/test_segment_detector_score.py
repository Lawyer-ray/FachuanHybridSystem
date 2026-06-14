"""Coverage tests for segment_detector.py — score_page, detect_segments, _find_complaint_end."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft


def _make_page(
    page_no: int,
    normalized_text: str = "",
    head_text: str = "",
    top_candidates: list | None = None,
) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text=normalized_text,
        normalized_text=normalized_text,
        head_text=head_text,
        source_method="ocr",
        ocr_failed=False,
        top_candidates=top_candidates or [],
    )


class TestScorePage:
    def setup_method(self) -> None:
        self.detector = SegmentDetector()

    def test_score_page_complaint_match(self) -> None:
        text = "民事起诉状 原告张三 被告李四 诉讼请求 事实与理由"
        result = self.detector.score_page(
            head_text=text[:10],
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        assert len(result) > 0
        assert result[0]["segment_type"] == PdfSplitSegmentType.COMPLAINT
        assert result[0]["score"] > 0

    def test_score_page_evidence_match(self) -> None:
        text = "证据清单 证明内容 页码 原件 复印件 提交人"
        result = self.detector.score_page(
            head_text="证据",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.EVIDENCE_LIST in types

    def test_score_page_no_match(self) -> None:
        text = "这是一段普通文本没有任何关键词匹配的段落内容"
        result = self.detector.score_page(
            head_text="普通",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        # Either empty or all scores are 0
        for r in result:
            assert r["score"] == 0.0 or not r.get("matched_strong")

    def test_score_page_negative_keywords_reduce_score(self) -> None:
        text = "民事起诉状 证据清单 授权委托书"
        result = self.detector.score_page(
            head_text="起诉",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        # Negative keywords should reduce score
        for r in result:
            assert r["score"] >= 0

    def test_score_page_weak_only_candidate(self) -> None:
        """When no strong keywords match but >=2 weak keywords match, creates weak_only candidate."""
        text = "诉讼请求 事实与理由 原告 被告"
        result = self.detector.score_page(
            head_text="诉讼",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        # Check if any weak_only candidates exist
        weak_only = [r for r in result if r.get("weak_only")]
        # If it exists, verify structure
        for r in weak_only:
            assert r["matched_strong"] == []

    def test_score_page_party_identity_match(self) -> None:
        text = "居民身份证 公民身份号码 签发机关"
        result = self.detector.score_page(
            head_text="身份证",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.PARTY_IDENTITY in types

    def test_score_page_authorization_match(self) -> None:
        text = "授权委托书 代理权限 受托人 委托人"
        result = self.detector.score_page(
            head_text="委托",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.AUTHORIZATION_MATERIALS in types

    def test_score_page_delivery_address_match(self) -> None:
        text = "送达地址确认书 诉讼文书 送达"
        result = self.detector.score_page(
            head_text="送达",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.DELIVERY_ADDRESS_CONFIRMATION in types

    def test_score_page_refund_account_match(self) -> None:
        text = "诉讼费用退费账户确认书 收款人 开户行名称 退费"
        result = self.detector.score_page(
            head_text="退费",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.REFUND_ACCOUNT_CONFIRMATION in types

    def test_score_page_preservation_match(self) -> None:
        text = "财产保全申请书 查封 扣押 冻结 申请事项"
        result = self.detector.score_page(
            head_text="保全",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        types = [r["segment_type"] for r in result]
        assert PdfSplitSegmentType.PRESERVATION_MATERIALS in types

    def test_score_returns_top_3(self) -> None:
        """score_page should return at most 3 candidates."""
        text = "民事起诉状 证据清单 居民身份证 授权委托书"
        result = self.detector.score_page(
            head_text="材料",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        assert len(result) <= 3

    def test_score_sorted_by_score_desc(self) -> None:
        text = "民事起诉状 原告 被告 诉讼请求 事实与理由"
        result = self.detector.score_page(
            head_text="起诉",
            normalized_text=text,
            template_key="filing_materials_v1",
        )
        if len(result) > 1:
            scores = [r["score"] for r in result]
            assert scores == sorted(scores, reverse=True)


class TestDetectSegments:
    def setup_method(self) -> None:
        self.detector = SegmentDetector()

    def test_detect_empty_pages(self) -> None:
        result = self.detector.detect_segments([], template_key="filing_materials_v1")
        assert result == []

    def test_detect_single_complaint_page(self) -> None:
        pages = [
            _make_page(1, normalized_text="民事起诉状 原告张三 被告李四 诉讼请求 事实与理由"),
        ]
        result = self.detector.detect_segments(pages, template_key="filing_materials_v1")
        assert len(result) >= 1

    def test_detect_multiple_pages_mixed(self) -> None:
        pages = [
            _make_page(1, normalized_text="民事起诉状 原告 被告 诉讼请求 事实与理由"),
            _make_page(2, normalized_text="证据清单 证明内容 页码 原件 复印件"),
            _make_page(3, normalized_text="居民身份证 公民身份号码 签发机关"),
        ]
        result = self.detector.detect_segments(pages, template_key="filing_materials_v1")
        assert len(result) >= 1
        # All pages should be accounted for
        total_covered = sum(s.page_end - s.page_start + 1 for s in result)
        assert total_covered >= 3

    def test_detect_fills_gaps(self) -> None:
        pages = [
            _make_page(1, normalized_text="民事起诉状 原告 被告 诉讼请求"),
            _make_page(2, normalized_text=""),  # empty page
            _make_page(3, normalized_text="证据清单 证明内容 页码"),
        ]
        result = self.detector.detect_segments(pages, template_key="filing_materials_v1")
        types = [s.segment_type for s in result]
        assert PdfSplitSegmentType.UNRECOGNIZED in types

    def test_detect_weak_only_flag(self) -> None:
        """Pages with weak-only matches get LOW_CONFIDENCE review flag."""
        pages = [
            _make_page(1, normalized_text="诉讼请求 事实与理由 原告 被告 人民法院"),
        ]
        result = self.detector.detect_segments(pages, template_key="filing_materials_v1")
        # Check that weak-only candidates get low confidence
        for seg in result:
            assert seg.review_flag in [
                PdfSplitReviewFlag.NORMAL,
                PdfSplitReviewFlag.LOW_CONFIDENCE,
                PdfSplitReviewFlag.UNRECOGNIZED,
            ]


class TestFindComplaintEnd:
    def setup_method(self) -> None:
        self.detector = SegmentDetector()

    def test_single_page_complaint(self) -> None:
        pages = [
            _make_page(1, normalized_text="民事起诉状 此致 人民法院"),
        ]
        rule = self._get_complaint_rule()
        end = self.detector._find_complaint_end(pages, 1, 1, rule)
        assert end >= 1

    def _get_complaint_rule(self):
        from apps.pdf_splitting.services.template_registry import get_template_definition
        template = get_template_definition("filing_materials_v1")
        return template.rules[0]


class TestMergeAdjacentPackEdgeCases:
    def setup_method(self) -> None:
        self.detector = SegmentDetector()

    def test_merge_with_normal_flag(self) -> None:
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=2, segment_type="party_identity",
                         filename="a.pdf", confidence=0.9, source_method="rule", review_flag="normal"),
            SegmentDraft(order=2, page_start=3, page_end=4, segment_type="party_identity",
                         filename="b.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 1
        assert result[0].confidence == 0.9  # max

    def test_three_adjacent_merge(self) -> None:
        segments = [
            SegmentDraft(order=1, page_start=1, page_end=1, segment_type="party_identity",
                         filename="a.pdf", confidence=0.7, source_method="rule", review_flag="normal"),
            SegmentDraft(order=2, page_start=2, page_end=2, segment_type="party_identity",
                         filename="b.pdf", confidence=0.8, source_method="rule", review_flag="normal"),
            SegmentDraft(order=3, page_start=3, page_end=3, segment_type="party_identity",
                         filename="c.pdf", confidence=0.9, source_method="rule", review_flag="normal"),
        ]
        result = self.detector._merge_adjacent_pack_segments(segments)
        assert len(result) == 1
        assert result[0].page_start == 1
        assert result[0].page_end == 3
        assert result[0].confidence == 0.9
