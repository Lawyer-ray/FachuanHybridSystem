"""补充覆盖测试: finance/services/calculator/schedule.py

覆盖: annuity_payment 零利率分支、first_due_date 钳制、is_offday /
shift_workday、status 判定、reschedule 各分支（等额本金/缩期/月供递减/
早退条件）。
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, Decimal
from types import SimpleNamespace

from apps.finance.services.calculator.mortgage_models import (
    CENT,
    PREPAY_REDUCE_PAYMENT,
    PREPAY_SHORTEN_TERM,
    REPAYMENT_EQUAL_INSTALLMENT,
    REPAYMENT_EQUAL_PRINCIPAL,
    STATUS_PAID,
    STATUS_PARTIAL,
    STATUS_UNPAID,
)
from apps.finance.services.calculator.schedule import (
    annuity_payment,
    first_due_date,
    is_offday,
    reschedule,
    shift_workday,
    status,
)

# ── annuity_payment ───────────────────────────────────────────────


class TestAnnuityPayment:
    def test_zero_rate_divides_balance_ceiling(self):
        result = annuity_payment(Decimal("1000"), Decimal("0"), 3)
        assert result == (Decimal("1000") / Decimal(3)).quantize(CENT, rounding=ROUND_CEILING)

    def test_zero_rate_exact_division(self):
        # 整除时无进位：1200 / 12 = 100
        result = annuity_payment(Decimal("1200"), Decimal("0"), 12)
        assert result == Decimal("100")
        assert result == result.quantize(CENT, rounding=ROUND_CEILING)

    def test_formula_value(self):
        # 100000 元、年化 3.6%、12 期：月利率 0.003
        bal = Decimal("100000")
        annual = Decimal("3.6")
        months = 12
        i = annual / Decimal("100") / Decimal("12")
        factor = (Decimal(1) + i) ** months
        expected = bal * i * factor / (factor - Decimal(1))
        assert annuity_payment(bal, annual, months) == expected


# ── first_due_date ────────────────────────────────────────────────


class TestFirstDueDate:
    def test_uses_start_day_when_payment_day_none(self):
        # 放款 2026-01-15 → 首期 2026-02-15
        assert first_due_date(date(2026, 1, 15), None) == date(2026, 2, 15)

    def test_payment_day_10(self):
        assert first_due_date(date(2026, 1, 15), 10) == date(2026, 2, 10)

    def test_payment_day_31_clamped_to_month_end(self):
        # 2 月无 31 日 → 收拢到 2/28
        assert first_due_date(date(2026, 1, 15), 31) == date(2026, 2, 28)

    def test_start_day_31_rolls_to_february_end(self):
        # 放款 1/31，未指定扣款日 → 2 月钳制到月末
        assert first_due_date(date(2026, 1, 31), None) == date(2026, 2, 28)

    def test_candidate_before_start_pushed_next_month(self):
        # 放款 1 月 1 日、扣款日 1 → 次月候选 2/1 合法，无需再顺延
        assert first_due_date(date(2026, 1, 1), 1) == date(2026, 2, 1)

    def test_end_of_month_start(self):
        # 放款 2026-01-31 → 次月候选日 2/28（钳制）
        assert first_due_date(date(2026, 1, 30), 30) == date(2026, 2, 28)


# ── is_offday / shift_workday ─────────────────────────────────────


class TestOffdayHelpers:
    def test_saturday_is_offday(self):
        assert is_offday(date(2026, 10, 3), set()) is True  # 周六

    def test_sunday_is_offday(self):
        assert is_offday(date(2026, 10, 4), set()) is True  # 周日

    def test_holiday_is_offday(self):
        assert is_offday(date(2026, 10, 5), {date(2026, 10, 5)}) is True

    def test_workday(self):
        assert is_offday(date(2026, 10, 5), set()) is False  # 周一

    def test_shift_over_weekend(self):
        # 10-03 周六 → 顺延到 10-05 周一
        assert shift_workday(date(2026, 10, 3), set()) == date(2026, 10, 5)

    def test_shift_over_holiday_chain(self):
        # 10-05（周一）为假日 → 顺延到 10-06
        assert shift_workday(date(2026, 10, 5), {date(2026, 10, 5)}) == date(2026, 10, 6)

    def test_workday_not_shifted(self):
        assert shift_workday(date(2026, 10, 5), set()) == date(2026, 10, 5)


# ── status ────────────────────────────────────────────────────────


class TestStatus:
    def test_paid_when_no_shortfall(self):
        assert status(Decimal("0"), Decimal("-0.01")) == STATUS_PAID

    def test_partial_when_small_shortfalls(self):
        # 欠付 < 1 元 → 部分归还
        assert status(Decimal("0.5"), Decimal("0.5")) == STATUS_PARTIAL

    def test_unpaid_when_large_shortfalls(self):
        assert status(Decimal("100"), Decimal("100")) == STATUS_UNPAID

    def test_partial_when_principal_negative_only(self):
        # 本金多还、利息欠付 → 交叉符号走 PARTIAL
        assert status(Decimal("-5"), Decimal("100")) == STATUS_PARTIAL


# ── reschedule ────────────────────────────────────────────────────


def _make_sim(**overrides: object) -> SimpleNamespace:
    defaults: dict = {
        "reschedule_count": 0,
        "remaining_periods": 24,
        "balance": Decimal("800000"),
        "current_rate": Decimal("4.2"),
        "repayment_method": REPAYMENT_EQUAL_INSTALLMENT,
        "prepayment_handling": PREPAY_REDUCE_PAYMENT,
        "principal_part_plan": Decimal("0"),
        "monthly_payment": Decimal("5000"),
        "warnings": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestReschedule:
    def test_no_remaining_periods_returns_early(self):
        sim = _make_sim(remaining_periods=0)
        reschedule(sim, date(2026, 1, 15))
        assert sim.reschedule_count == 1
        assert sim.monthly_payment == Decimal("5000")  # 未重排

    def test_zero_balance_returns_early(self):
        sim = _make_sim(balance=Decimal("0"))
        reschedule(sim, date(2026, 1, 15))
        assert sim.reschedule_count == 1
        assert sim.monthly_payment == Decimal("5000")

    def test_equal_principal_reduce_payment_recomputes_plan(self):
        sim = _make_sim(
            repayment_method=REPAYMENT_EQUAL_PRINCIPAL,
            prepayment_handling=PREPAY_REDUCE_PAYMENT,
        )
        reschedule(sim, date(2026, 1, 15))
        assert sim.principal_part_plan == Decimal("800000") / Decimal(24)
        assert sim.monthly_payment == Decimal("5000")  # 等额本金不改月供

    def test_equal_principal_shorten_term_no_op(self):
        sim = _make_sim(
            repayment_method=REPAYMENT_EQUAL_PRINCIPAL,
            prepayment_handling=PREPAY_SHORTEN_TERM,
        )
        reschedule(sim, date(2026, 1, 15))
        assert sim.principal_part_plan == Decimal("0")
        assert sim.reschedule_count == 1

    def test_shorten_term_insufficient_payment_downgrades(self):
        # 月供 ≤ 当期利息 → 降级为月供递减并告警
        i = Decimal("4.2") / Decimal("100") / Decimal("12")
        sim = _make_sim(
            prepayment_handling=PREPAY_SHORTEN_TERM,
            monthly_payment=i * Decimal("800000"),  # 恰好等于当期利息
        )
        reschedule(sim, date(2026, 1, 15))
        assert sim.prepayment_handling == PREPAY_REDUCE_PAYMENT
        assert sim.monthly_payment == annuity_payment(Decimal("800000"), Decimal("4.2"), 24)
        assert any("不足以" in w for w in sim.warnings)

    def test_shorten_term_non_positive_ratio_recomputes_annuity(self):
        # ratio = 1 - i*balance/monthly_payment ≤ 0 → 直接按年金重算
        i = Decimal("4.2") / Decimal("100") / Decimal("12")
        sim = _make_sim(
            prepayment_handling=PREPAY_SHORTEN_TERM,
            monthly_payment=i * Decimal("800000"),  # ratio == 0
        )
        reschedule(sim, date(2026, 1, 15))
        assert sim.monthly_payment == annuity_payment(Decimal("800000"), Decimal("4.2"), 24)
        assert sim.remaining_periods == 24

    def test_shorten_term_normal_reduces_periods(self):
        # 月供远高于利息 → 计算所需期数并收缩
        sim = _make_sim(
            prepayment_handling=PREPAY_SHORTEN_TERM,
            monthly_payment=Decimal("20000"),
            balance=Decimal("200000"),
        )
        reschedule(sim, date(2026, 1, 15))
        assert 0 < sim.remaining_periods < 24

    def test_shorten_term_capped_by_original_periods(self):
        # 月供仅略高于当期利息 → 理论所需期数极长，被原期数封顶
        sim = _make_sim(
            prepayment_handling=PREPAY_SHORTEN_TERM,
            monthly_payment=Decimal("3000"),  # i*800000 ≈ 2800
        )
        reschedule(sim, date(2026, 1, 15))
        assert sim.remaining_periods == 24

    def test_reduce_payment_recomputes_annuity(self):
        sim = _make_sim(prepayment_handling=PREPAY_REDUCE_PAYMENT)
        reschedule(sim, date(2026, 1, 15))
        assert sim.monthly_payment == annuity_payment(Decimal("800000"), Decimal("4.2"), 24)
        assert sim.remaining_periods == 24
