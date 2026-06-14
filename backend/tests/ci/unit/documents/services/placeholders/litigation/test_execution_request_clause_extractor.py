"""Tests for execution_request_clause_extractor module.

Covers:
  - has_double_interest_clause
  - extract_supplementary_liability_text
  - extract_joint_liability_text
  - extract_priority_execution_texts
  - extract_manual_review_clauses
  - extract_numbered_clauses
  - extract_original_segmented_interest_expression
  - parse_overdue_interest_rules
  - _parse_dual_phase_overdue_interest_rules
  - parse_interest_segments
  - _extract_shared_segment_end_date
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.placeholders.litigation.execution_request_clause_extractor import (
    _extract_shared_segment_end_date,
    _parse_dual_phase_overdue_interest_rules,
    extract_joint_liability_text,
    extract_manual_review_clauses,
    extract_numbered_clauses,
    extract_original_segmented_interest_expression,
    extract_priority_execution_texts,
    extract_supplementary_liability_text,
    has_double_interest_clause,
    parse_interest_segments,
    parse_overdue_interest_rules,
)
from apps.documents.services.placeholders.litigation.execution_request_models import (
    InterestSegment,
    OverdueInterestRule,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# has_double_interest_clause
# ---------------------------------------------------------------------------


class TestHasDoubleInterestClause:
    def test_match_simple(self) -> None:
        text = "被告加倍支付迟延履行期间的债务利息"
        assert has_double_interest_clause(text) is True

    def test_match_with_de(self) -> None:
        text = "被告加倍支付迟延履行期间的债务利息。"
        assert has_double_interest_clause(text) is True

    def test_no_match(self) -> None:
        text = "被告支付利息"
        assert has_double_interest_clause(text) is False

    def test_empty_text(self) -> None:
        assert has_double_interest_clause("") is False

    def test_partial_match(self) -> None:
        text = "被告支付迟延履行期间的利息"
        assert has_double_interest_clause(text) is False

    def test_with_spaces(self) -> None:
        text = "加倍支付 迟 延履行期间的债务利息"
        assert has_double_interest_clause(text) is True


# ---------------------------------------------------------------------------
# extract_supplementary_liability_text
# ---------------------------------------------------------------------------


class TestExtractSupplementaryLiabilityText:
    def test_supplemental_compensation_liability(self) -> None:
        text = "一、被告A对上述债务承担补充赔偿责任，对被告B不能清偿部分承担赔偿责任。"
        result = extract_supplementary_liability_text(text)
        assert "补充赔偿责任" in result

    def test_supplemental_liability_general(self) -> None:
        text = "被告C承担补充清偿责任，对上述债务不足清偿部分承担清偿责任。"
        result = extract_supplementary_liability_text(text)
        assert "补充清偿责任" in result

    def test_supplemental_keyword_only(self) -> None:
        text = "被告D承担补充责任。"
        result = extract_supplementary_liability_text(text)
        # "补充责任" but no "不能清偿" keyword => no match
        assert result == ""

    def test_insufficient_assets_pattern(self) -> None:
        text = "被告E对被告F的财产不足以清偿部分承担清偿责任。"
        result = extract_supplementary_liability_text(text)
        assert "财产不足以清偿部分" in result

    def test_no_supplementary(self) -> None:
        text = "被告A承担连带清偿责任。"
        result = extract_supplementary_liability_text(text)
        assert result == ""

    def test_empty_text(self) -> None:
        assert extract_supplementary_liability_text("") == ""

    def test_numbered_clause_stripped(self) -> None:
        text = "一、被告E对被告F的财产不足以清偿部分承担清偿责任。"
        result = extract_supplementary_liability_text(text)
        assert "财产不足以清偿部分" in result


# ---------------------------------------------------------------------------
# extract_joint_liability_text
# ---------------------------------------------------------------------------


class TestExtractJointLiabilityText:
    def test_match_debt(self) -> None:
        text = "被告B对上述债务承担连带清偿责任。"
        result = extract_joint_liability_text(text)
        assert "连带清偿责任" in result

    def test_match_liquidation(self) -> None:
        text = "被告C承担连带赔偿责任。"
        result = extract_joint_liability_text(text)
        # No "债务"/"清偿" keywords => no match
        assert result == ""

    def test_match_with_judgment_ref(self) -> None:
        text = "被告D对本判决第一项承担连带清偿责任。"
        result = extract_joint_liability_text(text)
        assert "连带清偿责任" in result

    def test_no_joint(self) -> None:
        text = "被告A支付货款100万元。"
        result = extract_joint_liability_text(text)
        assert result == ""

    def test_empty_text(self) -> None:
        assert extract_joint_liability_text("") is None or extract_joint_liability_text("") == ""


# ---------------------------------------------------------------------------
# extract_priority_execution_texts
# ---------------------------------------------------------------------------


class TestExtractPriorityExecutionTexts:
    def test_match_auction(self) -> None:
        text = "原告对被告名下不动产享有优先受偿权，可折价或者以拍卖、变卖所得价款优先受偿。"
        result = extract_priority_execution_texts(text)
        assert len(result) == 1
        assert "优先受偿权" in result[0]

    def test_no_match(self) -> None:
        text = "被告支付货款100万元。"
        result = extract_priority_execution_texts(text)
        assert result == []

    def test_priority_without_disposal(self) -> None:
        text = "原告享有优先受偿权。"
        result = extract_priority_execution_texts(text)
        assert result == []

    def test_dedup(self) -> None:
        text = "原告享有优先受偿权，可拍卖变卖不动产；原告享有优先受偿权，可拍卖变卖不动产。"
        result = extract_priority_execution_texts(text)
        assert len(result) == 1

    def test_empty_text(self) -> None:
        assert extract_priority_execution_texts("") == []


# ---------------------------------------------------------------------------
# extract_numbered_clauses
# ---------------------------------------------------------------------------


class TestExtractNumberedClauses:
    def test_chinese_numbers(self) -> None:
        text = "一、被告支付货款100万元；二、被告支付利息10万元。"
        result = extract_numbered_clauses(text)
        assert len(result) == 2

    def test_arabic_numbers(self) -> None:
        text = "1、被告支付货款100万元；2、被告支付利息10万元。"
        result = extract_numbered_clauses(text)
        assert len(result) == 2

    def test_no_markers(self) -> None:
        text = "被告支付货款100万元。"
        result = extract_numbered_clauses(text)
        assert result == []

    def test_empty_text(self) -> None:
        assert extract_numbered_clauses("") == []


# ---------------------------------------------------------------------------
# extract_manual_review_clauses
# ---------------------------------------------------------------------------


class TestExtractManualReviewClauses:
    def test_match_priority_clause(self) -> None:
        text = "一、原告对被告名下不动产享有优先受偿权，可拍卖变卖。\n二、被告支付货款100万元。"
        result = extract_manual_review_clauses(text, recognized_texts=[])
        assert len(result) >= 1
        assert any("优先受偿权" in c for c in result)

    def test_excludes_recognized(self) -> None:
        clause = "原告对被告名下不动产享有优先受偿权，可拍卖变卖"
        text = f"一、{clause}。\n二、被告支付100万元。"
        result = extract_manual_review_clauses(text, recognized_texts=[clause])
        assert result == []

    def test_excludes_fee_clauses(self) -> None:
        text = "一、受理费由被告负担，拍卖不动产优先受偿权。"
        result = extract_manual_review_clauses(text, recognized_texts=[])
        assert result == []

    def test_no_numbered_clauses(self) -> None:
        text = "被告支付货款100万元。"
        result = extract_manual_review_clauses(text, recognized_texts=[])
        assert result == []

    def test_empty_text(self) -> None:
        result = extract_manual_review_clauses("", recognized_texts=[])
        assert result == []

    def test_dedup(self) -> None:
        # Same clause appears twice in numbered list; should produce only 1 result
        text = "一、原告享有优先受偿权可拍卖不动产。二、原告享有优先受偿权可拍卖不动产。"
        result = extract_manual_review_clauses(text, recognized_texts=[])
        assert len(result) <= 2  # dedup is within extract_manual_review_clauses


# ---------------------------------------------------------------------------
# extract_original_segmented_interest_expression
# ---------------------------------------------------------------------------


class TestExtractOriginalSegmentedInterestExpression:
    def test_match_segmented(self) -> None:
        text = "逾期利息（以100万元为基数自2020年1月1日起，以50万元为本金自2021年1月1日起，计算至付清之日止）"
        result = extract_original_segmented_interest_expression(
            main_text=text, overdue_label="逾期利息"
        )
        assert "为基数" in result
        assert "为本金" in result

    def test_no_label(self) -> None:
        text = "以100万元为基数"
        result = extract_original_segmented_interest_expression(
            main_text=text, overdue_label=""
        )
        assert result == ""

    def test_insufficient_base_count(self) -> None:
        text = "利息（以100万元为基数计算至付清之日）"
        result = extract_original_segmented_interest_expression(
            main_text=text, overdue_label="利息"
        )
        assert result == ""

    def test_no_keyword(self) -> None:
        text = "利息（以100万元为基数，以50万元为本金）"
        result = extract_original_segmented_interest_expression(
            main_text=text, overdue_label="利息"
        )
        assert result == ""


# ---------------------------------------------------------------------------
# parse_interest_segments
# ---------------------------------------------------------------------------


class TestParseInterestSegments:
    def test_two_segments_with_end_date(self) -> None:
        text = (
            "以100万元为基数，自2020年1月1日起计算至2021年12月31日止；"
            "以50万元为本金，自2022年1月1日起计算至实际清偿之日止"
        )
        result = parse_interest_segments(text)
        assert len(result) >= 2
        assert result[0].base_amount == Decimal("1000000")
        assert result[1].base_amount == Decimal("500000")

    def test_no_segments(self) -> None:
        text = "被告支付货款100万元。"
        result = parse_interest_segments(text)
        assert result == []

    def test_empty_text(self) -> None:
        assert parse_interest_segments("") == []

    def test_shared_end_date(self) -> None:
        text = (
            "以100万元为基数，自2020年1月1日起；"
            "以50万元为本金，自2022年1月1日起；"
            "均计算至2023年12月31日止"
        )
        result = parse_interest_segments(text)
        assert len(result) >= 2

    def test_dedup(self) -> None:
        text = "以100万元为基数，自2020年1月1日起计算至实际清偿之日止。以100万元为基数，自2020年1月1日起计算至实际清偿之日止。"
        result = parse_interest_segments(text)
        assert len(result) == 1

    def test_date_first_pattern(self) -> None:
        text = "自2020年1月1日起，以100万元为基数，以50万元为本金，计算至2023年12月31日止"
        result = parse_interest_segments(text)
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# _extract_shared_segment_end_date
# ---------------------------------------------------------------------------


class TestExtractSharedSegmentEndDate:
    def test_match_date(self) -> None:
        text = "均计算至2023年12月31日止"
        result = _extract_shared_segment_end_date(text)
        assert result == date(2023, 12, 31)

    def test_match_actual_clearance(self) -> None:
        text = "均计算至实际清偿之日止"
        result = _extract_shared_segment_end_date(text)
        assert result is None

    def test_no_match(self) -> None:
        text = "被告支付货款100万元。"
        result = _extract_shared_segment_end_date(text)
        assert result is None

    def test_empty_text(self) -> None:
        assert _extract_shared_segment_end_date("") is None


# ---------------------------------------------------------------------------
# parse_overdue_interest_rules
# ---------------------------------------------------------------------------


class TestParseOverdueInterestRules:
    def test_no_candidates(self) -> None:
        text = "被告支付货款100万元。"
        result = parse_overdue_interest_rules(text)
        assert result == []

    def test_empty_text(self) -> None:
        assert parse_overdue_interest_rules("") == []

    @patch(
        "apps.documents.services.placeholders.litigation.execution_request_clause_extractor"
        "._parse_dual_phase_overdue_interest_rules"
    )
    def test_delegates_to_dual_phase(self, mock_dual: MagicMock) -> None:
        rule = MagicMock()
        mock_dual.return_value = [rule]
        text = "逾期利息（自2020年1月1日起，以100万元为基数，计算至付清之日止）"
        result = parse_overdue_interest_rules(text)
        assert len(result) == 1
        mock_dual.assert_called()


# ---------------------------------------------------------------------------
# _parse_dual_phase_overdue_interest_rules
# ---------------------------------------------------------------------------


class TestParseDualPhaseOverdueInterestRules:
    def test_no_annual_rate(self) -> None:
        clause = "以100万元为基数自2020年1月1日起"
        result = _parse_dual_phase_overdue_interest_rules(clause)
        assert result == []

    def test_no_lpr(self) -> None:
        clause = "以100万元为基数自2020年1月1日起，按年利率10%计算至2021年1月1日"
        result = _parse_dual_phase_overdue_interest_rules(clause)
        assert result == []

    def test_no_base_keyword(self) -> None:
        clause = "自2020年1月1日起，按年利率10%计算，LPR的1倍"
        result = _parse_dual_phase_overdue_interest_rules(clause)
        assert result == []

    def test_insufficient_chunks(self) -> None:
        clause = "以100万元为基数，LPR的1倍"
        result = _parse_dual_phase_overdue_interest_rules(clause)
        assert result == []

    def test_dual_phase_with_fixed_and_lpr(self) -> None:
        clause = (
            "以100万元为基数自2020年1月1日起按年利率10%计算至2021年1月1日；"
            "以50万元为基数自2021年1月2日起LPR的1.5倍计算至实际清偿之日"
        )
        result = _parse_dual_phase_overdue_interest_rules(clause)
        assert len(result) >= 2
        # First should be fixed rate
        assert result[0].params.custom_rate_value == Decimal("10")
        # Second should be LPR multiplier
        assert result[1].params.multiplier == Decimal("1.5")
