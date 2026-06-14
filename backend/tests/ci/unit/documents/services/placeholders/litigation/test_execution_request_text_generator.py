"""Tests for execution_request_text_generator module.

Covers:
  - generate_request_text
  - build_fee_desc
  - build_interest_segment_desc
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.documents.services.placeholders.litigation.execution_request_models import (
    InterestSegment,
    ParsedAmounts,
    ParsedInterestParams,
)
from apps.documents.services.placeholders.litigation.execution_request_text_generator import (
    build_fee_desc,
    build_interest_segment_desc,
    generate_request_text,
)


# ---------------------------------------------------------------------------
# build_fee_desc
# ---------------------------------------------------------------------------


class TestBuildFeeDesc:
    def test_all_fees(self) -> None:
        amounts = ParsedAmounts(
            litigation_fee=Decimal("10000"),
            preservation_fee=Decimal("5000"),
            announcement_fee=Decimal("2000"),
            attorney_fee=Decimal("30000"),
            guarantee_fee=Decimal("8000"),
        )
        result = build_fee_desc(amounts)
        assert "受理费" in result
        assert "财产保全费" in result
        assert "公告费" in result
        assert "律师代理费" in result
        assert "财产保全担保费" in result

    def test_no_fees(self) -> None:
        amounts = ParsedAmounts()
        result = build_fee_desc(amounts)
        assert result == ""

    def test_single_fee(self) -> None:
        amounts = ParsedAmounts(litigation_fee=Decimal("10000"))
        result = build_fee_desc(amounts)
        assert result == "受理费10000元"


# ---------------------------------------------------------------------------
# build_interest_segment_desc
# ---------------------------------------------------------------------------


class TestBuildInterestSegmentDesc:
    def test_two_segments(self) -> None:
        segments = [
            InterestSegment(base_amount=Decimal("1000000"), start_date=date(2020, 1, 1), end_date=date(2020, 12, 31)),
            InterestSegment(base_amount=Decimal("500000"), start_date=date(2021, 1, 1), end_date=date(2021, 6, 30)),
        ]
        result = build_interest_segment_desc(segments)
        assert "1000000元" in result
        assert "500000元" in result

    def test_segment_without_end(self) -> None:
        segments = [
            InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1), end_date=None),
        ]
        result = build_interest_segment_desc(segments)
        assert "实际清偿之日止" in result

    def test_empty(self) -> None:
        assert build_interest_segment_desc([]) == ""


# ---------------------------------------------------------------------------
# generate_request_text
# ---------------------------------------------------------------------------


class TestGenerateRequestText:
    def test_basic_with_principal(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号《判决书》",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
        )
        assert "100000元" in result
        assert "合计" in result
        assert "执行费用" in result

    def test_fee_only_no_principal(self) -> None:
        amounts = ParsedAmounts(litigation_fee=Decimal("10000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("10000"),
            has_double_interest_clause=False,
        )
        assert "受理费" in result

    def test_no_amounts(self) -> None:
        amounts = ParsedAmounts()
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("0"),
            has_double_interest_clause=False,
        )
        assert "支付款项" in result

    def test_confirmed_interest(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"), confirmed_interest=Decimal("10000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("110000"),
            has_double_interest_clause=False,
        )
        assert "利息10000元" in result

    def test_overdue_interest_with_rate(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            multiplier=Decimal("1.5"),
            rate_description="LPR的1.5倍",
        )
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("5000"),
            interest_base=Decimal("100000"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("105000"),
            has_double_interest_clause=False,
        )
        assert "利息" in result
        assert "5000元" in result

    def test_double_interest_clause(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=True,
        )
        assert "加倍支付" in result

    def test_joint_liability(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            joint_liability_text="被告B承担连带清偿责任",
        )
        assert "连带清偿责任" in result

    def test_supplementary_liability(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            supplementary_liability_text="被告C承担补充赔偿责任",
        )
        assert "补充赔偿责任" in result

    def test_priority_texts(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            priority_execution_texts=["原告对不动产享有优先受偿权，可拍卖变卖"],
        )
        assert "优先受偿权" in result

    def test_manual_review_clauses(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            manual_review_clauses=["原告对股权享有优先受偿权"],
        )
        assert "人工核对" in result
        assert "股权" in result

    def test_custom_interest_summary(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("5000"),
            interest_base=Decimal("100000"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("105000"),
            has_double_interest_clause=False,
            custom_interest_summary="利息按判决规则计算，截至2026年1月1日利息为5000元",
        )
        assert "判决规则" in result

    def test_segmented_interest(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams(
            multiplier=Decimal("1"),
            rate_description="LPR",
        )
        segments = [
            InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1), end_date=date(2020, 12, 31)),
            InterestSegment(base_amount=Decimal("50000"), start_date=date(2021, 1, 1)),
        ]
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("5000"),
            interest_base=Decimal("100000"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("105000"),
            has_double_interest_clause=False,
            interest_segments=segments,
        )
        assert "5000元" in result

    def test_segmented_with_original_expression(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams(
            multiplier=Decimal("1"),
            rate_description="LPR",
        )
        segments = [
            InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1), end_date=date(2020, 12, 31)),
            InterestSegment(base_amount=Decimal("50000"), start_date=date(2021, 1, 1)),
        ]
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("5000"),
            interest_base=Decimal("100000"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("105000"),
            has_double_interest_clause=False,
            interest_segments=segments,
            original_segmented_interest_expression="以100万元为基数自2020年1月1日起，以50万元为本金自2021年1月1日起",
        )
        assert "100万元" in result or "基数" in result

    def test_fee_with_principal(self) -> None:
        amounts = ParsedAmounts(
            principal=Decimal("100000"),
            litigation_fee=Decimal("10000"),
        )
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("110000"),
            has_double_interest_clause=False,
        )
        assert "受理费" in result

    def test_empty_joint_liability_text(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            joint_liability_text="",
        )
        # Should not crash

    def test_empty_priority_text_item(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        params = ParsedInterestParams()
        result = generate_request_text(
            full_case_number="(2026)粤01号",
            amounts=amounts,
            params=params,
            overdue_interest=Decimal("0"),
            interest_base=Decimal("0"),
            cutoff_date=date(2026, 1, 1),
            total=Decimal("100000"),
            has_double_interest_clause=False,
            priority_execution_texts=["", "有效的优先受偿权文本"],
        )
        assert "优先受偿权" in result
