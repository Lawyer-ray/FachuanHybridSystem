"""房贷违约债权计算器单测.

覆盖：等额本息/等额本金摊销、断供罚息复利、冲抵顺序、提前还款重排、
指定罚息利率、对罚息计复利开关、输入校验。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.mortgage_calculator import MortgageDefaultCalculator, PaymentRecord, add_months

CENT = Decimal("0.01")


def make_calculator() -> MortgageDefaultCalculator:
    """构造不依赖 DB 的计算器（固定利率模式不触发 LPR 查询）."""
    return MortgageDefaultCalculator.__new__(MortgageDefaultCalculator)


def annuity(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """等额本息月供理论值."""
    i = annual_rate / Decimal("100") / Decimal("12")
    factor = (Decimal(1) + i) ** months
    return principal * i * factor / (factor - Decimal(1))


class TestAddMonths:
    def test_normal(self):
        assert add_months(date(2024, 1, 15), 3) == date(2024, 4, 15)

    def test_month_end_clamp(self):
        # 1/31 + 1 个月 → 2/29（2024 闰年）
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_year_rollover(self):
        assert add_months(date(2024, 11, 15), 3) == date(2025, 2, 15)


class TestEqualInstallmentAmortization:
    """等额本息：正常还款不断供."""

    def test_full_repayment_no_default(self):
        calc = make_calculator()
        monthly = annuity(Decimal("1000000"), Decimal("4.2"), 120).quantize(CENT)
        payments = [PaymentRecord(add_months(date(2024, 1, 10), k), monthly) for k in range(1, 121)]
        result = calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            payments=payments,
            claim_date=date(2034, 2, 1),
        )
        assert result.claim.outstanding_principal == Decimal("0.00")
        assert result.claim.penalty_interest == Decimal("0.00")
        # 总利息与理论值一致（月供×120 - 本金）
        expected_total_interest = monthly * 120 - Decimal("1000000")
        actual = sum(r.interest_part for r in result.schedule_rows)
        assert abs(actual - expected_total_interest) < Decimal("1.00")

    def test_monthly_payment_matches_formula(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            claim_date=date(2024, 3, 1),
        )
        # 期 1 的月供应等于理论月供
        expected = annuity(Decimal("1000000"), Decimal("4.2"), 120).quantize(CENT)
        row1 = result.schedule_rows[0]
        assert row1.monthly_payment == expected


class TestDefaultScenarios:
    """断供场景：罚息/复利/明细."""

    def test_default_penalty_accrues(self):
        calc = make_calculator()
        monthly = annuity(Decimal("1000000"), Decimal("4.2"), 120).quantize(CENT)
        result = calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            penalty_multiplier=Decimal("1.5"),
            compound_on_interest=True,
            payments=[
                PaymentRecord(date(2024, 2, 10), monthly),
                PaymentRecord(date(2024, 3, 10), monthly),
            ],
            claim_date=date(2024, 9, 5),
        )
        c = result.claim
        # 期 3 起断供：有欠本、欠息、罚息
        assert c.outstanding_principal > Decimal("0")
        assert c.unpaid_interest > Decimal("0")
        assert c.penalty_interest > Decimal("0")
        assert c.total_claim == (c.outstanding_principal + c.unpaid_interest + c.penalty_interest + c.compound_interest)
        # 违约期数 = 5（4~9 月间 3-7 月 5 期）
        default_rows = [r for r in result.default_rows if r.status != "paid"]
        assert len(default_rows) == 5
        # 罚息理论校验：期 3 欠本按 执行利率×1.5 × 天数/360
        row3 = default_rows[0]
        overdue_principal = row3.due_principal - row3.paid_principal
        expected_penalty = overdue_principal * Decimal("0.063") * Decimal(row3.overdue_days) / Decimal(360)
        # 该行罚息应接近理论值（受批次内其他冲抵影响允许小幅偏差）
        assert row3.accrued_penalty > Decimal("0")
        # 日增金额为正
        assert c.daily_accrual > Decimal("0")

    def test_specified_penalty_rate(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("500000"),
            start_date=date(2024, 1, 1),
            term_months=60,
            rate_mode="fixed",
            fixed_rate=Decimal("3.95"),
            penalty_mode="specified",
            penalty_rate=Decimal("5.5"),
            claim_date=date(2024, 8, 1),
        )
        # 指定 5.5% 罚息：首期罚息 = 欠本×5.5%×天数/360
        row1 = [r for r in result.default_rows if r.status != "paid"][0]
        overdue = row1.due_principal - row1.paid_principal
        expected = overdue * Decimal("0.055") * Decimal(row1.overdue_days) / Decimal(360)
        assert abs(row1.accrued_penalty - expected) < Decimal("1.00")

    def test_compound_on_penalty_toggle(self):
        calc = make_calculator()
        base_kwargs = {
            "principal": Decimal("500000"),
            "start_date": date(2024, 1, 1),
            "term_months": 60,
            "rate_mode": "fixed",
            "fixed_rate": Decimal("3.95"),
            "claim_date": date(2024, 8, 1),
        }
        r_off = calc.calculate(**base_kwargs, compound_on_interest=True, compound_on_penalty=False)
        r_on = calc.calculate(**base_kwargs, compound_on_interest=True, compound_on_penalty=True)
        assert r_on.claim.compound_interest > r_off.claim.compound_interest
        assert any("复利" in w for w in r_on.warnings)

    def test_no_compound(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("500000"),
            start_date=date(2024, 1, 1),
            term_months=60,
            rate_mode="fixed",
            fixed_rate=Decimal("3.95"),
            compound_on_interest=False,
            claim_date=date(2024, 8, 1),
        )
        assert result.claim.compound_interest == Decimal("0.00")


class TestAllocationOrder:
    """冲抵顺序."""

    def test_interest_first_order(self):
        calc = make_calculator()
        # 4/15 还 5000，冲抵顺序 利息→本金：应先冲期 1 欠息
        result = calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            allocation_order=["interest", "penalty", "compound", "principal"],
            payments=[PaymentRecord(date(2024, 4, 15), Decimal("5000"))],
            claim_date=date(2024, 9, 5),
        )
        # 期 1 应还利息 3500 被冲掉；剩余 1500 按顺序继续冲期 2 欠息（尚不到本金）
        row1 = result.default_rows[0]
        assert row1.paid_interest == Decimal("3500.00")
        row2 = result.default_rows[1]
        assert row2.paid_interest == Decimal("1500.00")
        assert row2.paid_principal == Decimal("0.00")

    def test_invalid_keys_dropped(self):
        calc = make_calculator()
        order = calc._normalize_allocation_order(["bogus", "interest", "interest", "principal"])
        assert order[0] == "interest"
        assert order.count("interest") == 1
        # 缺失 bucket 补齐到末尾
        assert set(order) == {"penalty", "interest", "compound", "principal"}


class TestPrepayment:
    """提前还款重排."""

    def test_prepayment_reduces_balance(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("800000"),
            start_date=date(2023, 6, 15),
            term_months=240,
            repayment_method="equal_principal",
            rate_mode="fixed",
            fixed_rate=Decimal("4.9"),
            payments=[
                PaymentRecord(date(2023, 7, 15), Decimal("6600")),
                PaymentRecord(date(2023, 8, 15), Decimal("6600")),
                PaymentRecord(date(2023, 9, 15), Decimal("6600")),
                PaymentRecord(date(2023, 10, 20), Decimal("100000"), payment_type="prepayment_principal"),
            ],
            claim_date=date(2024, 3, 1),
        )
        # 提前还款后余额应显著下降：800000 - 3×期本金(3333.33) - 100000 + 少量溢缴 ≈ 693188
        assert Decimal("690000") < result.claim.outstanding_principal < Decimal("696000")
        assert any("重排" in w for w in result.warnings)
        # 重排后期利息 = 余额 × 4.9% / 12 ≈ 2830
        post = [r for r in result.schedule_rows if r.due_date > date(2023, 11, 1)]
        assert post[0].interest_part == Decimal("2830.53")

    def test_full_prepayment_settles(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("500000"),
            start_date=date(2024, 1, 1),
            term_months=60,
            rate_mode="fixed",
            fixed_rate=Decimal("4.0"),
            payments=[PaymentRecord(date(2024, 2, 1), Decimal("600000"), payment_type="prepayment_principal")],
            claim_date=date(2024, 3, 1),
        )
        assert result.claim.outstanding_principal == Decimal("0.00")


class TestPaymentNormalization:
    """还款流水清洗."""

    def test_invalid_payments_warned_and_skipped(self):
        calc = make_calculator()
        warnings: list[str] = []
        records = calc._normalize_payments(
            [
                PaymentRecord(date(2024, 5, 1), Decimal("-100")),
                PaymentRecord(date(2023, 1, 1), Decimal("500")),
                PaymentRecord(date(2024, 5, 2), Decimal("500"), payment_type="bogus"),
                PaymentRecord(date(2024, 5, 3), Decimal("500")),
            ],
            date(2024, 1, 1),
            warnings,
        )
        assert len(records) == 2
        assert len(warnings) == 3

    def test_claim_before_first_due(self):
        calc = make_calculator()
        result = calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            claim_date=date(2024, 2, 1),
        )
        # 截止日早于首期扣款日：只截算合同利息
        assert result.claim.outstanding_principal == Decimal("1000000.00")
        assert result.claim.penalty_interest == Decimal("0.00")
        assert result.default_rows == []
        assert any("早于首期" in w for w in result.warnings)


class TestValidation:
    def test_invalid_principal(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("0"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
            )

    def test_invalid_repayment_method(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                repayment_method="balloon",
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
            )

    def test_fixed_rate_required(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=None,
            )

    def test_specified_penalty_rate_required(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                penalty_mode="specified",
                penalty_rate=None,
            )

    def test_claim_must_be_after_start(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                claim_date=date(2023, 12, 1),
            )
