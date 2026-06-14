"""Tests for execution_request_interest module.

Covers:
  - parse_interest_params (LPR, LPR markup, plain LPR, fixed rate, permille, permyriad, daily percent, date, cap, base rule)
  - detect_overdue_item_label
  - infer_principal_from_interest_base
  - parse_interest_base_rule
  - resolve_interest_base
  - parse_deduction_order
  - _map_deduction_token
  - apply_paid_amount
  - calculate_interest
  - calculate_interest_with_segments
  - extract_interest_clause
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.placeholders.litigation.execution_request_interest import (
    _map_deduction_token,
    apply_paid_amount,
    calculate_interest,
    calculate_interest_with_segments,
    detect_overdue_item_label,
    extract_interest_clause,
    infer_principal_from_interest_base,
    parse_deduction_order,
    parse_interest_base_rule,
    parse_interest_params,
    resolve_interest_base,
)
from apps.documents.services.placeholders.litigation.execution_request_models import (
    InterestSegment,
    ParsedAmounts,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# parse_interest_params
# ---------------------------------------------------------------------------


class TestParseInterestParams:
    def test_lpr_multiplier(self) -> None:
        text = "按全国银行间同业拆借中心公布的一年期贷款市场报价利率的1.5倍计算"
        params = parse_interest_params(text)
        assert params.multiplier == Decimal("1.5")
        assert params.rate_type == "1y"
        assert "1.5倍" in params.rate_description

    def test_lpr_markup(self) -> None:
        text = "按全国银行间同业拆借中心公布的一年期贷款市场报价利率上浮30%计算"
        params = parse_interest_params(text)
        assert params.multiplier == Decimal("1.3")
        assert params.rate_type == "1y"

    def test_plain_lpr(self) -> None:
        text = "按全国银行间同业拆借中心公布的一年期贷款市场报价利率计算"
        params = parse_interest_params(text)
        assert params.multiplier == Decimal("1")
        assert params.rate_type == "1y"

    def test_fixed_rate(self) -> None:
        text = "按年利率10%计算"
        params = parse_interest_params(text)
        assert params.custom_rate_unit == "percent"
        assert params.custom_rate_value == Decimal("10")

    def test_daily_permille(self) -> None:
        text = "按日利率千分之五计算"
        params = parse_interest_params(text)
        assert params.custom_rate_unit == "permille"
        assert params.custom_rate_value == Decimal("5")

    def test_daily_permyriad(self) -> None:
        text = "按日利率万分之五计算"
        params = parse_interest_params(text)
        assert params.custom_rate_unit == "permyriad"
        assert params.custom_rate_value == Decimal("5")

    def test_daily_percent(self) -> None:
        text = "按日利率0.05%计算"
        params = parse_interest_params(text)
        assert params.custom_rate_unit == "permyriad"

    def test_start_date(self) -> None:
        text = "自2020年1月15日起按年利率10%计算"
        params = parse_interest_params(text)
        assert params.start_date == date(2020, 1, 15)

    def test_no_rate(self) -> None:
        text = "被告支付货款100万元"
        params = parse_interest_params(text)
        assert params.multiplier is None
        assert params.custom_rate_value is None

    def test_overdue_label(self) -> None:
        text = "逾期付款违约金按年利率10%计算"
        params = parse_interest_params(text)
        # "逾期付款违约金" is the highest priority label
        assert params.overdue_item_label == "逾期付款违约金"

    def test_interest_cap_pattern_a(self) -> None:
        text = "以不超过100000元为限。按年利率10%计算"
        params = parse_interest_params(text)
        assert params.interest_cap == Decimal("100000")

    def test_interest_cap_pattern_b(self) -> None:
        text = "利息总额不超过200000元。按年利率10%计算"
        params = parse_interest_params(text)
        assert params.interest_cap == Decimal("200000")

    def test_lpr_chinese_multiplier(self) -> None:
        text = "按全国银行间同业拆借中心公布的一年期贷款市场报价利率的两倍计算"
        params = parse_interest_params(text)
        assert params.multiplier == Decimal("2")


# ---------------------------------------------------------------------------
# detect_overdue_item_label
# ---------------------------------------------------------------------------


class TestDetectOverdueItemLabel:
    def test_overdue_payment_penalty(self) -> None:
        assert detect_overdue_item_label("逾期付款违约金按年利率10%计算") == "逾期付款违约金"

    def test_penalty_with_calc_markers(self) -> None:
        # "违约金" alone without calc markers won't trigger
        assert detect_overdue_item_label("违约金按年利率10%计算") == "违约金"

    def test_overdue_payment_loss(self) -> None:
        assert detect_overdue_item_label("逾期付款损失按LPR计算") == "逾期付款损失"

    def test_overdue_payment_interest(self) -> None:
        assert detect_overdue_item_label("逾期付款利息按LPR计算") == "逾期付款利息"

    def test_overdue_interest(self) -> None:
        assert detect_overdue_item_label("逾期利息按LPR计算") == "逾期利息"

    def test_default_interest(self) -> None:
        assert detect_overdue_item_label("被告支付货款100万元") == "利息"

    def test_empty(self) -> None:
        assert detect_overdue_item_label("") == "利息"


# ---------------------------------------------------------------------------
# infer_principal_from_interest_base
# ---------------------------------------------------------------------------


class TestInferPrincipalFromInterestBase:
    def test_fixed_amount(self) -> None:
        params = ParsedInterestParams(base_mode="fixed_amount", base_amount=Decimal("100000"))
        result = infer_principal_from_interest_base(params)
        assert result == Decimal("100000")

    def test_fixed_amount_remaining(self) -> None:
        params = ParsedInterestParams(base_mode="fixed_amount_remaining", base_amount=Decimal("50000"))
        result = infer_principal_from_interest_base(params)
        assert result == Decimal("50000")

    def test_zero_base(self) -> None:
        params = ParsedInterestParams(base_mode="fixed_amount", base_amount=Decimal("0"))
        result = infer_principal_from_interest_base(params)
        assert result is None

    def test_no_base(self) -> None:
        params = ParsedInterestParams(base_mode="remaining_principal")
        result = infer_principal_from_interest_base(params)
        assert result is None

    def test_none_base(self) -> None:
        params = ParsedInterestParams(base_mode="fixed_amount", base_amount=None)
        result = infer_principal_from_interest_base(params)
        assert result is None


# ---------------------------------------------------------------------------
# parse_interest_base_rule
# ---------------------------------------------------------------------------


class TestParseInterestBaseRule:
    def test_fixed_amount_in_text(self) -> None:
        rate_text = "以100000元为本金"
        full_text = "以100000元为本金计算利息"
        mode, amount = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "fixed_amount"
        assert amount == Decimal("100000")

    def test_remaining_amount(self) -> None:
        rate_text = "以剩余未付100000元为本金"
        full_text = "以剩余未付100000元为本金"
        mode, amount = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "fixed_amount_remaining"

    def test_remaining_principal(self) -> None:
        rate_text = "以借款为基数"
        full_text = "以借款为基数"
        mode, amount = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "remaining_principal"

    def test_remaining_total(self) -> None:
        rate_text = "以未付款项为基数"
        full_text = "以未付款项为基数"
        mode, amount = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "remaining_total"

    def test_fallback_target(self) -> None:
        rate_text = "按年利率10%计算"
        full_text = "按年利率10%计算"
        mode, amount = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "fallback_target"

    def test_compact_text_remaining_principal(self) -> None:
        rate_text = "按年利率10%计算"
        full_text = "以未偿还借款为基数按年利率10%计算"
        mode, _ = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "remaining_principal"

    def test_compact_text_remaining_total(self) -> None:
        rate_text = "按年利率10%计算"
        full_text = "以上述款项为基数按年利率10%计算"
        mode, _ = parse_interest_base_rule(rate_text=rate_text, full_text=full_text)
        assert mode == "remaining_total"


# ---------------------------------------------------------------------------
# resolve_interest_base
# ---------------------------------------------------------------------------


class TestResolveInterestBase:
    def test_fixed_amount(self) -> None:
        case = MagicMock()
        case.target_amount = None
        amounts = ParsedAmounts(principal=Decimal("80000"))
        params = ParsedInterestParams(base_mode="fixed_amount", base_amount=Decimal("100000"))
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("100000")

    def test_fixed_amount_with_payment(self) -> None:
        case = MagicMock()
        case.target_amount = None
        amounts = ParsedAmounts(principal=Decimal("80000"))
        params = ParsedInterestParams(base_mode="fixed_amount", base_amount=Decimal("100000"))
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("30000"))
        assert result == Decimal("70000")

    def test_remaining_principal(self) -> None:
        case = MagicMock()
        case.target_amount = None
        amounts = ParsedAmounts(principal=Decimal("80000"))
        params = ParsedInterestParams(base_mode="remaining_principal")
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("80000")

    def test_remaining_total(self) -> None:
        case = MagicMock()
        case.target_amount = None
        amounts = ParsedAmounts(principal=Decimal("80000"), confirmed_interest=Decimal("20000"))
        params = ParsedInterestParams(base_mode="remaining_total")
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("100000")

    def test_fallback_target(self) -> None:
        case = MagicMock()
        case.target_amount = Decimal("150000")
        amounts = ParsedAmounts()
        params = ParsedInterestParams(base_mode="fallback_target")
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("150000")

    def test_base_zero_fallback_to_target(self) -> None:
        case = MagicMock()
        case.target_amount = Decimal("200000")
        amounts = ParsedAmounts(principal=Decimal("0"))
        params = ParsedInterestParams(base_mode="remaining_principal")
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("200000")

    def test_base_zero_no_target(self) -> None:
        case = MagicMock()
        case.target_amount = None
        amounts = ParsedAmounts(principal=Decimal("50000"))
        params = ParsedInterestParams(base_mode="remaining_principal")
        result = resolve_interest_base(case=case, amounts=amounts, params=params, principal_paid=Decimal("0"))
        assert result == Decimal("50000")  # max(principal, 0)


# ---------------------------------------------------------------------------
# parse_deduction_order
# ---------------------------------------------------------------------------


class TestParseDeductionOrder:
    def test_normal(self) -> None:
        text = "按受理费、利息、本金的顺序优先进行抵扣"
        result = parse_deduction_order(text)
        assert "litigation_fee" in result
        assert "interest" in result
        assert "principal" in result

    def test_pattern_b(self) -> None:
        text = "按受理费、本金抵扣顺序"
        result = parse_deduction_order(text)
        assert "litigation_fee" in result
        assert "principal" in result

    def test_no_match(self) -> None:
        text = "被告支付货款100万元"
        result = parse_deduction_order(text)
        assert result == []

    def test_empty(self) -> None:
        assert parse_deduction_order("") == []

    def test_dedup(self) -> None:
        text = "按受理费、受理费的顺序进行抵扣"
        result = parse_deduction_order(text)
        assert result.count("litigation_fee") == 1


# ---------------------------------------------------------------------------
# _map_deduction_token
# ---------------------------------------------------------------------------


class TestMapDeductionToken:
    def test_litigation_fee(self) -> None:
        assert _map_deduction_token("受理费") == "litigation_fee"

    def test_preservation_fee(self) -> None:
        assert _map_deduction_token("保全费") == "preservation_fee"

    def test_announcement_fee(self) -> None:
        assert _map_deduction_token("公告费") == "announcement_fee"

    def test_attorney_fee(self) -> None:
        assert _map_deduction_token("律师费") == "attorney_fee"

    def test_guarantee_fee(self) -> None:
        assert _map_deduction_token("担保费") == "guarantee_fee"

    def test_interest(self) -> None:
        assert _map_deduction_token("利息") == "interest"

    def test_principal(self) -> None:
        assert _map_deduction_token("本金") == "principal"

    def test_unknown(self) -> None:
        assert _map_deduction_token("未知") is None

    def test_preservation_excludes_guarantee(self) -> None:
        # "保全" + "担保" => guarantee_fee (first match in code is "担保")
        assert _map_deduction_token("保全担保费") == "guarantee_fee"

    def test_principal_variant(self) -> None:
        assert _map_deduction_token("借款本金") == "principal"

    def test_overdue_interest(self) -> None:
        assert _map_deduction_token("逾期利息") == "interest"


# ---------------------------------------------------------------------------
# apply_paid_amount
# ---------------------------------------------------------------------------


class TestApplyPaidAmount:
    def test_no_deduction_order(self) -> None:
        amounts = ParsedAmounts(
            principal=Decimal("100000"),
            confirmed_interest=Decimal("10000"),
            litigation_fee=Decimal("5000"),
        )
        result, principal_paid, applied = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("30000"),
            deduction_order=[],
        )
        assert principal_paid > 0
        assert result.principal < Decimal("100000")

    def test_with_deduction_order(self) -> None:
        amounts = ParsedAmounts(
            principal=Decimal("100000"),
            confirmed_interest=Decimal("10000"),
            litigation_fee=Decimal("5000"),
        )
        result, principal_paid, applied = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("30000"),
            deduction_order=["litigation_fee", "interest", "principal"],
        )
        assert result.litigation_fee == Decimal("0")
        assert result.confirmed_interest == Decimal("0")
        assert len(applied) >= 2

    def test_zero_paid(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        result, principal_paid, applied = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("0"),
            deduction_order=["principal"],
        )
        assert principal_paid == Decimal("0")
        assert result.principal == Decimal("100000")

    def test_negative_paid(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        result, principal_paid, applied = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("-5000"),
            deduction_order=[],
        )
        assert principal_paid == Decimal("0")

    def test_paid_exceeds_all(self) -> None:
        amounts = ParsedAmounts(
            principal=Decimal("10000"),
            confirmed_interest=Decimal("1000"),
        )
        result, principal_paid, applied = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("100000"),
            deduction_order=["principal"],
        )
        assert result.principal == Decimal("0")

    def test_unknown_key_in_deduction_order(self) -> None:
        amounts = ParsedAmounts(principal=Decimal("100000"))
        result, _, _ = apply_paid_amount(
            amounts=amounts,
            paid_amount=Decimal("50000"),
            deduction_order=["unknown_key"],
        )
        # Should still deduct from principal
        assert result.principal == Decimal("50000")


# ---------------------------------------------------------------------------
# calculate_interest
# ---------------------------------------------------------------------------


class TestCalculateInterest:
    def test_zero_principal(self) -> None:
        calculator = MagicMock()
        params = ParsedInterestParams(start_date=date(2020, 1, 1), multiplier=Decimal("1"))
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("0"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_no_start_date(self) -> None:
        calculator = MagicMock()
        params = ParsedInterestParams(multiplier=Decimal("1"))
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_no_rate(self) -> None:
        calculator = MagicMock()
        params = ParsedInterestParams(start_date=date(2020, 1, 1))
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_cutoff_before_start(self) -> None:
        calculator = MagicMock()
        params = ParsedInterestParams(start_date=date(2021, 1, 1), multiplier=Decimal("1"))
        warnings: list[str] = []
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2020, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=warnings,
        )
        assert result == Decimal("0")
        assert len(warnings) == 1

    def test_custom_rate(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("10000")
        calculator.calculate.return_value = calc_result
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            custom_rate_unit="percent",
            custom_rate_value=Decimal("10"),
        )
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("10000")

    def test_multiplier(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("5000")
        calculator.calculate.return_value = calc_result
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            multiplier=Decimal("1.5"),
        )
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("5000")

    def test_interest_cap(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("50000")
        calculator.calculate.return_value = calc_result
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            multiplier=Decimal("1"),
            interest_cap=Decimal("30000"),
        )
        warnings: list[str] = []
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=warnings,
        )
        assert result == Decimal("30000")
        assert any("上限" in w for w in warnings)

    def test_calculator_exception(self) -> None:
        calculator = MagicMock()
        calculator.calculate.side_effect = TypeError("error")
        params = ParsedInterestParams(
            start_date=date(2020, 1, 1),
            multiplier=Decimal("1"),
        )
        warnings: list[str] = []
        result = calculate_interest(
            calculator=calculator,
            principal=Decimal("100000"),
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=warnings,
        )
        assert result == Decimal("0")
        assert any("失败" in w for w in warnings)


# ---------------------------------------------------------------------------
# calculate_interest_with_segments
# ---------------------------------------------------------------------------


class TestCalculateInterestWithSegments:
    def test_empty_segments(self) -> None:
        calculator = MagicMock()
        params = ParsedInterestParams(multiplier=Decimal("1"))
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=[],
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_no_rate(self) -> None:
        calculator = MagicMock()
        segments = [InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1))]
        params = ParsedInterestParams()
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_normal_segments(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("8000")
        calculator.calculate_with_principal_changes.return_value = calc_result
        segments = [
            InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1), end_date=date(2020, 12, 31)),
            InterestSegment(base_amount=Decimal("50000"), start_date=date(2021, 1, 1), end_date=date(2021, 6, 30)),
        ]
        params = ParsedInterestParams(multiplier=Decimal("1"))
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 6, 30),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("8000")

    def test_interest_cap(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("50000")
        calculator.calculate_with_principal_changes.return_value = calc_result
        segments = [InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1))]
        params = ParsedInterestParams(multiplier=Decimal("1"), interest_cap=Decimal("30000"))
        warnings: list[str] = []
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=warnings,
        )
        assert result == Decimal("30000")

    def test_segment_end_before_start(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("0")
        calculator.calculate_with_principal_changes.return_value = calc_result
        segments = [InterestSegment(base_amount=Decimal("100000"), start_date=date(2021, 1, 1), end_date=date(2020, 1, 1))]
        params = ParsedInterestParams(multiplier=Decimal("1"))
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 6, 30),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("0")

    def test_calculator_exception(self) -> None:
        calculator = MagicMock()
        calculator.calculate_with_principal_changes.side_effect = ValueError("err")
        segments = [InterestSegment(base_amount=Decimal("100000"), start_date=date(2020, 1, 1))]
        params = ParsedInterestParams(multiplier=Decimal("1"))
        warnings: list[str] = []
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 1, 1),
            year_days=365,
            date_inclusion="both",
            warnings=warnings,
        )
        assert result == Decimal("0")
        assert any("失败" in w for w in warnings)

    def test_segment_clamped_to_cutoff(self) -> None:
        calculator = MagicMock()
        calc_result = MagicMock()
        calc_result.total_interest = Decimal("1000")
        calculator.calculate_with_principal_changes.return_value = calc_result
        segments = [
            InterestSegment(
                base_amount=Decimal("100000"),
                start_date=date(2020, 1, 1),
                end_date=date(2025, 1, 1),  # far future
            )
        ]
        params = ParsedInterestParams(multiplier=Decimal("1"))
        result = calculate_interest_with_segments(
            calculator=calculator,
            segments=segments,
            params=params,
            cutoff_date=date(2021, 6, 30),
            year_days=365,
            date_inclusion="both",
            warnings=[],
        )
        assert result == Decimal("1000")
        # Verify the end_date was clamped to cutoff
        call_args = calculator.calculate_with_principal_changes.call_args
        periods = call_args.kwargs["principal_periods"]
        assert periods[0].end_date == date(2021, 6, 30)


# ---------------------------------------------------------------------------
# extract_interest_clause
# ---------------------------------------------------------------------------


class TestExtractInterestClause:
    def test_lpr_pattern(self) -> None:
        text = "被告支付货款。按全国银行间同业拆借中心公布的一年期贷款市场报价利率的1.5倍计算利息。"
        result = extract_interest_clause(text)
        assert "LPR" in result or "贷款市场报价利率" in result

    def test_annual_rate(self) -> None:
        text = "被告支付货款。按年利率10%计算利息。"
        result = extract_interest_clause(text)
        assert "年利率" in result

    def test_daily_rate(self) -> None:
        text = "被告支付货款。按日利率万分之五计算利息。"
        result = extract_interest_clause(text)
        assert "日利率" in result

    def test_no_match_returns_full_text(self) -> None:
        text = "被告支付货款100万元"
        result = extract_interest_clause(text)
        assert result == text
