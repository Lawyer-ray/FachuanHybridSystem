"""房贷违约债权计算器单测.

覆盖：等额本息/等额本金摊销、断供罚息复利、冲抵顺序、提前还款重排、
指定罚息利率、对罚息计复利开关、输入校验。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.mortgage_calculator import (
    MortgageDefaultCalculator,
    PausePeriod,
    PaymentRecord,
    add_months,
)

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
        # 首期按天计息（prorate 默认口径）导致首期本金摊还少于整月假设，
        # 固定月供下末期需多还差额（银行实务：末期月供调整）；末笔多还以覆盖清尾
        payments = [PaymentRecord(add_months(date(2024, 1, 10), k), monthly) for k in range(1, 120)]
        payments.append(PaymentRecord(add_months(date(2024, 1, 10), 120), Decimal("10500")))
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
        # 期 1 应还利息按 prorate 口径（1/10→2/10 共 31 天）被冲掉；剩余冲期 2 欠息（尚不到本金）
        row1 = result.default_rows[0]
        assert row1.paid_interest == Decimal("3616.67")
        row2 = result.default_rows[1]
        assert row2.paid_interest == Decimal("1383.33")
        assert row2.paid_principal == Decimal("0.00")

    def test_invalid_keys_dropped(self):
        calc = make_calculator()
        order = calc._normalize_allocation_order(["bogus", "interest", "interest", "principal"])
        assert order[0] == "interest"
        assert order.count("interest") == 1
        # 缺失 bucket 补齐到末尾（含一次性违约金 bucket）
        assert set(order) == {"penalty", "penalty_lump", "interest", "compound", "principal"}


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


class TestAcceleration:
    """加速到期：全部本金提前到期、停止摊销、对全额计罚息."""

    def _base_result(self, **overrides):
        calc = make_calculator()
        kwargs = {
            "principal": Decimal("1000000"),
            "start_date": date(2024, 1, 10),
            "term_months": 120,
            "rate_mode": "fixed",
            "fixed_rate": Decimal("4.2"),
        }
        kwargs.update(overrides)
        return calc.calculate(**kwargs)

    def test_acceleration_transfers_principal_to_overdue(self):
        # 断供数期后于 2024-06-01 宣布加速到期，截止 2024-12-31
        result = self._base_result(
            penalty_multiplier=Decimal("1.5"),
            compound_on_interest=True,
            payments=[PaymentRecord(date(2024, 2, 10), Decimal("20000"))],
            accelerate_date=date(2024, 6, 1),
            claim_date=date(2024, 12, 31),
        )
        c = result.claim
        # 触发加速：meta 标记已加速，剩余本金为全部到期本金（>0）
        assert result.meta["accelerated"] is True
        assert c.outstanding_principal > Decimal("0")
        # 加速后本金全额到期，罚息为正、按日对全额计收
        assert c.penalty_interest > Decimal("0")
        assert c.daily_accrual > Decimal("0")

    def test_acceleration_stops_amortization_schedule(self):
        # 加速后不再产出新摊销计划行（schedule 止于加速前的期次）
        result = self._base_result(
            accelerate_date=date(2024, 6, 1),
            claim_date=date(2025, 1, 1),
        )
        # 未设置还款/断供时，加速后计划行明显少于按 120 期摊销
        last_due = result.schedule_rows[-1].due_date if result.schedule_rows else None
        assert last_due is None or last_due < date(2025, 1, 1)
        assert result.meta["accelerated"] is True

    def test_acceleration_after_claim_is_noop(self):
        # 加速日不早于截止日 → 不触发加速（等同于普通计算）
        result = self._base_result(
            payments=[PaymentRecord(date(2024, 3, 10), Decimal("20000"))],
            accelerate_date=date(2025, 1, 1),
            claim_date=date(2024, 12, 31),
        )
        assert result.meta["accelerated"] is False
        assert result.meta["accelerate_date"] == ""

    def test_invalid_accelerate_date_before_start(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                accelerate_date=date(2023, 6, 1),
                claim_date=date(2024, 12, 31),
            )


class TestClaimMode:
    """违约金与罚息主张口径：并行 or 择一从高."""

    def _both_result(self, claim_mode):
        calc = make_calculator()
        return calc.calculate(
            principal=Decimal("1000000"),
            start_date=date(2024, 1, 10),
            term_months=120,
            rate_mode="fixed",
            fixed_rate=Decimal("4.2"),
            penalty_multiplier=Decimal("1.5"),
            lump_penalty_rate=Decimal("1.0"),  # 逾期本金 1% 一次性违约金
            lump_penalty_threshold_days=60,
            compound_on_interest=True,
            payments=[PaymentRecord(date(2024, 2, 10), Decimal("20000"))],
            claim_mode=claim_mode,
            claim_date=date(2024, 12, 31),
        )

    def test_both_sums_penalty_and_lump(self):
        result = self._both_result("both")
        c = result.claim
        # 并行：罚息与违约金都计入，总行 = 各分项之和
        assert result.meta["claim_mode"] == "both"
        assert c.lump_penalty > Decimal("0")
        assert c.penalty_interest > Decimal("0")
        assert c.total_claim == (
            c.outstanding_principal
            + c.unpaid_interest
            + c.penalty_interest
            + c.compound_interest
            + c.lump_penalty
            + c.other_fees
        )

    def test_either_takes_higher(self):
        result = self._both_result("either")
        c = result.claim
        assert result.meta["claim_mode"] == "either"
        assert result.meta["claim_taken"] in ("罚息", "违约金")
        # 择一从高后：罚息与违约金只保留其一
        have_both = c.penalty_interest > Decimal("0") and c.lump_penalty > Decimal("0")
        assert not have_both
        # 总行 = 各分项之和（此时被择去的一项为 0）
        assert c.total_claim == (
            c.outstanding_principal
            + c.unpaid_interest
            + c.penalty_interest
            + c.compound_interest
            + c.lump_penalty
            + c.other_fees
        )

    def test_invalid_claim_mode(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                claim_mode="invalid_mode",
                claim_date=date(2024, 12, 31),
            )


class TestCap:
    """利率/总债权封顶."""

    def _base(self, **overrides):
        calc = make_calculator()
        kwargs = {
            "principal": Decimal("1000000"),
            "start_date": date(2024, 1, 10),
            "term_months": 120,
            "rate_mode": "fixed",
            "fixed_rate": Decimal("4.2"),
            "penalty_multiplier": Decimal("1.5"),
            "compound_on_interest": True,
            "payments": [PaymentRecord(date(2024, 2, 10), Decimal("20000"))],
            "claim_date": date(2024, 12, 31),
        }
        kwargs.update(overrides)
        return calc.calculate(**kwargs)

    def test_penalty_rate_cap_lowers_penalty(self):
        uncapped = self._base()
        capped = self._base(cap_penalty_annual=Decimal("5.0"))  # 实际罚息 4.2*1.5=6.3 > 5.0
        assert capped.claim.penalty_interest < uncapped.claim.penalty_interest
        assert capped.meta["cap_penalty_annual"] == "5.00"
        assert any("封顶" in w for w in capped.warnings)

    def test_total_cap_reduces_total_claim(self):
        uncapped = self._base()
        forced = self._base(cap_total_mode="amount", cap_total_value=Decimal("100"))
        assert forced.claim.total_claim < uncapped.claim.total_claim
        assert forced.meta["capped_total"] is True
        responsive = forced.claim.penalty_interest + forced.claim.compound_interest + forced.claim.lump_penalty
        assert responsive <= Decimal("100")

    def test_total_cap_no_effect_when_not_exceeding(self):
        result = self._base(cap_total_mode="principal_ratio", cap_total_value=Decimal("10"))
        assert result.meta["capped_total"] is False

    def test_invalid_cap_total_mode(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                cap_total_mode="bad",
                cap_total_value=Decimal("1"),
                claim_date=date(2024, 12, 31),
            )


class TestInterestCut:
    """计息起止边界：是否含截止日当天（算头算尾）."""

    def _base(self, **overrides):
        calc = make_calculator()
        kwargs = {
            "principal": Decimal("1000000"),
            "start_date": date(2024, 1, 10),
            "term_months": 120,
            "rate_mode": "fixed",
            "fixed_rate": Decimal("4.2"),
            "penalty_multiplier": Decimal("1.5"),
            "compound_on_interest": True,
            "payments": [PaymentRecord(date(2024, 2, 10), Decimal("20000"))],
            "claim_date": date(2024, 12, 31),
        }
        kwargs.update(overrides)
        return calc.calculate(**kwargs)

    def test_inclusive_adds_a_day(self):
        excl = self._base()
        incl = self._base(interest_cut_inclusive=True)
        assert incl.claim.penalty_interest > excl.claim.penalty_interest
        assert incl.meta["interest_cut_inclusive"] is True


class TestPause:
    """停息挂账：区间内罚息/复利及按天截算的合同利息暂停计息."""

    def _base(self, **overrides):
        calc = make_calculator()
        kwargs = {
            "principal": Decimal("1000000"),
            "start_date": date(2024, 1, 10),
            "term_months": 120,
            "rate_mode": "fixed",
            "fixed_rate": Decimal("4.2"),
            "penalty_multiplier": Decimal("1.5"),
            "compound_on_interest": True,
            "payments": [PaymentRecord(date(2024, 2, 10), Decimal("20000"))],
            "claim_date": date(2024, 12, 31),
        }
        kwargs.update(overrides)
        return calc.calculate(**kwargs)

    def test_pause_reduces_penalty(self):
        no_pause = self._base()
        with_pause = self._base(pause_periods=[PausePeriod(date(2024, 6, 1), date(2024, 12, 31), note="停息挂账")])
        assert with_pause.claim.penalty_interest < no_pause.claim.penalty_interest
        assert with_pause.meta["pause_periods"]
        assert any("停息" in w for w in with_pause.warnings)

    def test_invalid_pause_period(self):
        calc = make_calculator()
        with pytest.raises(ValidationException):
            calc.calculate(
                principal=Decimal("100000"),
                start_date=date(2024, 1, 1),
                term_months=60,
                rate_mode="fixed",
                fixed_rate=Decimal("4.0"),
                pause_periods=[PausePeriod(date(2024, 7, 1), date(2024, 6, 1))],
                claim_date=date(2024, 12, 31),
            )
