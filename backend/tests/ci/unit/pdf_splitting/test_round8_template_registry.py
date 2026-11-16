"""Tests for template_registry and segment_detector continuation logic."""

from __future__ import annotations

import pytest

from apps.pdf_splitting.models import PdfSplitSegmentType
from apps.pdf_splitting.services.split.segment_detector import SegmentDetector
from apps.pdf_splitting.services.template_registry import (
    SegmentTemplateRule,
    TemplateDefinition,
    get_default_filename,
    get_segment_label,
    get_template_definition,
)

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
        from apps.pdf_splitting.models import PdfSplitSegmentType
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        d1 = SegmentDraft(
            order=0,
            page_start=1,
            page_end=2,
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            filename="a.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
        d2 = SegmentDraft(
            order=1,
            page_start=5,
            page_end=6,
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            filename="b.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
        result = sd._merge_adjacent_pack_segments([d1, d2])
        assert len(result) == 2

    def test_adjacent_same_type(self):
        sd = SegmentDetector()
        from apps.pdf_splitting.models import PdfSplitSegmentType
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        d1 = SegmentDraft(
            order=0,
            page_start=1,
            page_end=2,
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            filename="a.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
        d2 = SegmentDraft(
            order=1,
            page_start=3,
            page_end=5,
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            filename="b.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
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


# ---------------------------------------------------------------------------
# P3-5：模板缺口 / 强制归类压力 / 空转代码
# ---------------------------------------------------------------------------


class TestOpenLabelHints:
    def test_仍无键名的高频材料列进提示(self):
        """收据/对账单等仍没有枚举键名，列出来让模型给准确开放名，
        而不是硬塞一个语义不对的既有键名。"""
        hints = get_template_definition("filing_materials_v1").open_label_hints
        for name in ("收据", "对账单", "催款函", "律师函", "结婚证", "出生医学证明", "不动产权属查询结果"):
            assert name in hints

    def test_已补键名的材料不再出现在提示里(self):
        """借条/转账回单/聊天记录/和解协议/保证合同已有贴切键名：
        同时出现在「可用键名」与「无键名提示」里会让模型自相矛盾。"""
        td = get_template_definition("filing_materials_v1")
        typed = {rule.label for rule in td.rules}
        for name in ("借条", "转账回单", "聊天记录", "和解协议", "保证合同"):
            assert name in typed
            assert name not in td.open_label_hints
        for name in ("欠条", "微信聊天记录", "还款协议", "担保函", "支付宝转账记录"):
            assert name not in td.open_label_hints

    def test_既有键名一个没动(self):
        """补开放命名提示与新增类型都不能破坏既有 type 键：落库仍受枚举约束。"""
        from apps.pdf_splitting.models import PdfSplitSegmentType

        td = get_template_definition("filing_materials_v1")
        assert len(td.rules) == 34
        valid = {choice for choice, _label in PdfSplitSegmentType.choices}
        assert all(rule.segment_type in valid for rule in td.rules)

    def test_新增类型的strong只收抬头式短语(self):
        """规则引擎扫全页：「提到借条」不等于「是借条」。
        strong 里混进正文常用词会把引用了借条的合同误切成借条。"""
        from apps.pdf_splitting.models import PdfSplitSegmentType

        td = get_template_definition("filing_materials_v1")
        new_types = {
            PdfSplitSegmentType.IOU,
            PdfSplitSegmentType.TRANSFER_RECEIPT,
            PdfSplitSegmentType.CHAT_RECORD,
            PdfSplitSegmentType.SETTLEMENT_AGREEMENT,
            PdfSplitSegmentType.GUARANTEE_CONTRACT,
        }
        rules = [rule for rule in td.rules if rule.segment_type in new_types]
        assert len(rules) == 5
        for rule in rules:
            assert rule.strong_keywords
            assert "借款" not in rule.strong_keywords
            assert "担保" not in rule.strong_keywords

    def test_二审模板默认无提示(self):
        assert get_template_definition("appeal_defense_v1").open_label_hints == ()

    def test_未知模板回退仍带提示(self):
        assert get_template_definition("nonexistent").open_label_hints


class TestPartyIdentityCoversHouseholdRegister:
    def test_户口簿归入主体信息(self):
        """户口簿与身份证同属当事人主体信息，枚举里已有贴切键名，
        不该让它落 unrecognized（民间借贷卷宗高频）。"""
        rule = next(
            r
            for r in get_template_definition("filing_materials_v1").rules
            if r.segment_type == PdfSplitSegmentType.PARTY_IDENTITY
        )
        assert "居民户口簿" in rule.strong_keywords
        assert "户口本" in rule.strong_keywords
        assert "常住人口登记卡" in rule.strong_keywords

    def test_户口簿页能被规则引擎认出(self):
        sd = SegmentDetector()
        candidates = sd.score_page(
            head_text="居民户口簿户主甲某",
            normalized_text="居民户口簿户主甲某与户主关系长子公民身份号码",
            template_key="filing_materials_v1",
        )
        assert candidates
        assert candidates[0]["segment_type"] == PdfSplitSegmentType.PARTY_IDENTITY


class TestPromptRuleSixSoftened:
    def test_不再强制有贴切键名就必须用(self):
        from apps.pdf_splitting.services.split.llm_segment_detector import SYSTEM_PROMPT

        assert "有贴切键名就必须用" not in SYSTEM_PROMPT
        assert "贴切才用" in SYSTEM_PROMPT
        assert "转账回单" in SYSTEM_PROMPT  # 举出硬塞的反例

    def test_仍保留不写死场景的约束(self):
        """二审包全回 other 的历史教训：system prompt 不能预设场景。"""
        from apps.pdf_splitting.services.split.llm_segment_detector import SYSTEM_PROMPT

        assert "立案材料整理助手" not in SYSTEM_PROMPT
        assert "不要用你自己对" in SYSTEM_PROMPT


class TestDeadContinuationInferenceRemoved:
    def test_空转的上下文推理已删除(self):
        """产出被三处跳过、对边界零影响，且无测试覆盖——留着只会误导读者
        以为规则引擎有跨页上下文推理。"""
        assert not hasattr(SegmentDetector, "_infer_continuation_pages")

    def test_删除后规则引擎边界不变(self):
        """相邻同类型段仍标 rule_adjacent_start（原来靠 prev_real 过滤 context_infer）。"""
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        def page(no: int, seg_type: str) -> PageDescriptor:
            return PageDescriptor(
                page_no=no,
                text="x",
                normalized_text="x",
                head_text="x",
                source_method="ocr",
                ocr_failed=False,
                top_candidates=[
                    {"segment_type": seg_type, "label": "l", "score": 0.8, "matched_strong": ["k"], "matched_weak": []}
                ],
                layout_title=f"标题{no}",
            )

        pages = [page(1, "evidence_list"), page(2, "evidence_list"), page(3, "bank_statement")]
        segments = SegmentDetector().detect_segments(pages, template_key="filing_materials_v1")
        adjacent = [s for s in segments if s.source_method == "rule_adjacent_start"]
        assert adjacent and adjacent[0].page_start == 2
        assert adjacent[0].review_flag == "low_confidence"
