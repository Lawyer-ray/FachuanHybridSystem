"""补充覆盖测试: finance/services/calculator/rate_resolver.py

覆盖: safe_date / last_repricing_date / _validate_events /
_base_contract_rate（固定与 LPR 快照二分 + 缓存）/ contract_annual 分段事件 /
penalty_annual / eff_penalty_annual（加码与封顶）。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.services.calculator.mortgage_models import PENALTY_MODE_SPECIFIED, RATE_MODE_FIXED, RATE_MODE_LPR
from apps.finance.services.calculator.rate_resolver import RateResolver, last_repricing_date, safe_date


def _make_resolver(**overrides: object) -> RateResolver:
    kwargs: dict = {
        "rate_mode": RATE_MODE_FIXED,
        "fixed_rate": Decimal("4.20"),
        "rate_service": None,
        "lpr_type": "5y",
        "basis_points": Decimal("0"),
        "repricing_day": "01-01",
        "start_date": date(2024, 6, 15),
        "rate_events": None,
        "penalty_mode": "multiplier",
        "penalty_multiplier": Decimal("1.5"),
        "penalty_rate": None,
        "cap_penalty_annual": None,
        "step_up_rate": None,
        "step_up_trigger_days": 90,
    }
    kwargs.update(overrides)
    return RateResolver(**kwargs)


# ── safe_date ─────────────────────────────────────────────────────


class TestSafeDate:
    def test_february_clamped_to_28(self):
        assert safe_date(2026, 2, 30) == date(2026, 2, 28)

    def test_february_leap_year_still_28(self):
        assert safe_date(2024, 2, 29) == date(2024, 2, 28)

    def test_31_day_clamped_to_30(self):
        assert safe_date(2026, 1, 31) == date(2026, 1, 30)

    def test_normal_day_unchanged(self):
        assert safe_date(2026, 3, 15) == date(2026, 3, 15)

    def test_day_30_in_february(self):
        assert safe_date(2026, 2, 15) == date(2026, 2, 15)


# ── last_repricing_date ───────────────────────────────────────────


class TestLastRepricingDate:
    def test_anniversary_same_year(self):
        # 放款 2024-06-15，周年重定价，on=2024-12-01 → 2024-06-15
        assert last_repricing_date(date(2024, 6, 15), date(2024, 12, 1), "anniversary") == date(2024, 6, 15)

    def test_anniversary_next_year(self):
        assert last_repricing_date(date(2024, 6, 15), date(2025, 3, 1), "anniversary") == date(2024, 6, 15)

    def test_anniversary_after_anniversary(self):
        assert last_repricing_date(date(2024, 6, 15), date(2025, 8, 1), "anniversary") == date(2025, 6, 15)

    def test_fixed_mm_dd(self):
        assert last_repricing_date(date(2024, 6, 15), date(2025, 5, 1), "01-01") == date(2025, 1, 1)

    def test_before_first_repricing_returns_start(self):
        # on 早于当年重定价日 → 回退到放款日
        assert last_repricing_date(date(2024, 6, 15), date(2024, 2, 1), "01-01") == date(2024, 6, 15)

    def test_anniversary_day_clamped_feb(self):
        # 放款 1/31 的周年日在 2 月被钳制到 2/28
        assert last_repricing_date(date(2024, 1, 31), date(2024, 3, 1), "anniversary") == date(2024, 1, 31)


# ── _validate_events ──────────────────────────────────────────────


class TestValidateEvents:
    def test_none_events_returns_empty_list(self):
        resolver = _make_resolver(rate_events=None)
        assert resolver.rate_events == []

    def test_missing_date_rejected(self):
        with pytest.raises(ValidationException, match="分段利率事件需同时提供"):
            _make_resolver(rate_events=[{"annual_rate": Decimal("4")}])

    def test_missing_annual_rate_rejected(self):
        with pytest.raises(ValidationException, match="分段利率事件需同时提供"):
            _make_resolver(rate_events=[{"date": "2026-01-01"}])

    def test_events_sorted_by_date(self):
        resolver = _make_resolver(
            rate_events=[
                {"date": "2026-06-01", "annual_rate": Decimal("4.5")},
                {"date": "2025-06-01", "annual_rate": Decimal("4.0")},
            ]
        )
        dates = [str(ev["date"]) for ev in resolver.rate_events]
        assert dates == ["2025-06-01", "2026-06-01"]


# ── contract_annual: 固定与分段事件 ────────────────────────────────


class TestContractAnnual:
    def test_fixed_mode_returns_fixed_rate(self):
        resolver = _make_resolver()
        assert resolver.contract_annual(date(2026, 3, 1)) == Decimal("4.20")

    def test_event_overrides_base(self):
        resolver = _make_resolver(rate_events=[{"date": "2025-01-01", "annual_rate": Decimal("5.5")}])
        assert resolver.contract_annual(date(2026, 1, 1)) == Decimal("5.5")

    def test_event_date_object_form(self):
        resolver = _make_resolver(rate_events=[{"date": date(2025, 1, 1), "annual_rate": Decimal("5.5")}])
        assert resolver.contract_annual(date(2026, 1, 1)) == Decimal("5.5")

    def test_before_event_uses_base(self):
        resolver = _make_resolver(rate_events=[{"date": "2026-01-01", "annual_rate": Decimal("5.5")}])
        assert resolver.contract_annual(date(2025, 12, 31)) == Decimal("4.20")

    def test_latest_applicable_event_wins(self):
        resolver = _make_resolver(
            rate_events=[
                {"date": "2025-01-01", "annual_rate": Decimal("5.0")},
                {"date": "2026-01-01", "annual_rate": Decimal("6.0")},
            ]
        )
        assert resolver.contract_annual(date(2026, 6, 1)) == Decimal("6.0")
        assert resolver.contract_annual(date(2025, 6, 1)) == Decimal("5.0")


# ── _base_contract_rate: LPR 快照 + 二分 + 缓存 ───────────────────


class TestBaseContractRateLpr:
    def _make_lpr_resolver(self, **overrides: object) -> tuple[RateResolver, MagicMock]:
        rate_service = MagicMock()
        rate_service.get_rates_snapshot.return_value = [
            (date(2024, 1, 1), Decimal("3.45"), Decimal("3.95")),
            (date(2025, 1, 1), Decimal("3.10"), Decimal("3.60")),
        ]
        rate_service.rate_at_from_snapshot.side_effect = lambda snapshot, q: (
            (Decimal("3.45"), Decimal("3.95")) if q < date(2025, 1, 1) else (Decimal("3.10"), Decimal("3.60"))
        )
        resolver = _make_resolver(
            rate_mode=RATE_MODE_LPR,
            fixed_rate=None,
            rate_service=rate_service,
            basis_points=Decimal("20"),
            **overrides,
        )
        return resolver, rate_service

    def test_lpr_5y_plus_basis_points(self):
        resolver, service = self._make_lpr_resolver()
        # 2026-01-05 的重定价日为 2026-01-01 → 2025 档 5y=3.60 + 20bp
        rate = resolver.contract_annual(date(2026, 1, 5))
        assert rate == Decimal("3.60") + Decimal("20") / Decimal("100")

    def test_lpr_1y_variant(self):
        resolver, service = self._make_lpr_resolver(lpr_type="1y")
        rate = resolver.contract_annual(date(2026, 6, 1))
        assert rate == Decimal("3.10") + Decimal("20") / Decimal("100")

    def test_repricing_day_picks_older_snapshot_row(self):
        # 重定价日为 6-15：2025-06 前的重定价日 2025-06-15 → 2025 档；
        # 但 2025-01-01 之前查询（如 2024-12-31 的重定价日 2024-06-15）→ 2024 档
        resolver, service = self._make_lpr_resolver(repricing_day="anniversary")
        early = resolver.contract_annual(date(2024, 12, 1))
        assert early == Decimal("3.95") + Decimal("20") / Decimal("100")

    def test_snapshot_passed_to_rate_at_query(self):
        resolver, service = self._make_lpr_resolver(repricing_day="anniversary")
        rate = resolver.contract_annual(date(2025, 3, 1))
        # 重定价日 = 放款日 2024-06-15 → 2024 档 5y=3.95 + 20bp
        assert rate == Decimal("3.95") + Decimal("20") / Decimal("100")
        service.rate_at_from_snapshot.assert_called_once()
        call_args = service.rate_at_from_snapshot.call_args
        assert call_args.args[1] == date(2024, 6, 15)  # 查询日为重定价日而非 on
        assert call_args.args[0] is service.get_rates_snapshot.return_value  # 同一快照对象

    @pytest.mark.django_db
    def test_real_service_with_lpr_rate_rows(self):
        """真实 LPRRateService：PYTEST 下快照绕过缓存直查库。"""
        from apps.finance.models.lpr_rate import LPRRate
        from apps.finance.services.lpr.rate_service import LPRRateService

        LPRRate.objects.create(
            effective_date=date(2024, 5, 20), rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"), source="test"
        )
        LPRRate.objects.create(
            effective_date=date(2025, 5, 20), rate_1y=Decimal("3.00"), rate_5y=Decimal("3.50"), source="test"
        )
        resolver = _make_resolver(
            rate_mode=RATE_MODE_LPR,
            fixed_rate=None,
            rate_service=LPRRateService(),
            lpr_type="5y",
            basis_points=Decimal("-10"),
            repricing_day="anniversary",
        )
        # 2025-08 的重定价日 2025-05-20 → 3.50 - 0.10
        assert resolver.contract_annual(date(2025, 8, 1)) == Decimal("3.40")
        # 2024-08 的重定价日 2024-05-20 → 3.95 - 0.10
        assert resolver.contract_annual(date(2024, 8, 1)) == Decimal("3.85")

    @pytest.mark.django_db
    def test_real_service_raises_before_first_rate(self):
        from apps.finance.models.lpr_rate import LPRRate
        from apps.finance.services.lpr.rate_service import LPRRateService

        LPRRate.objects.create(
            effective_date=date(2024, 5, 20), rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"), source="test"
        )
        # 放款日早于首条 LPR → 重定价日回退到放款日, 二分查不到数据
        resolver = _make_resolver(
            rate_mode=RATE_MODE_LPR,
            fixed_rate=None,
            rate_service=LPRRateService(),
            start_date=date(2020, 1, 1),
        )
        with pytest.raises(ValidationException, match="LPR利率数据"):
            resolver.contract_annual(date(2020, 6, 1))


# ── penalty_annual ────────────────────────────────────────────────


class TestPenaltyAnnual:
    def test_multiplier_mode(self):
        resolver = _make_resolver()  # 4.20 × 1.5
        assert resolver.penalty_annual(date(2026, 1, 1)) == Decimal("4.20") * Decimal("1.5")

    def test_specified_mode(self):
        resolver = _make_resolver(
            penalty_mode=PENALTY_MODE_SPECIFIED,
            penalty_rate=Decimal("8.4"),
        )
        assert resolver.penalty_annual(date(2026, 1, 1)) == Decimal("8.4")

    def test_cap_applied_to_multiplier(self):
        resolver = _make_resolver(cap_penalty_annual=Decimal("5.0"))
        assert resolver.penalty_annual(date(2026, 1, 1)) == Decimal("5.0")

    def test_cap_not_applied_when_below(self):
        resolver = _make_resolver(cap_penalty_annual=Decimal("9.9"))
        assert resolver.penalty_annual(date(2026, 1, 1)) == Decimal("4.20") * Decimal("1.5")


# ── eff_penalty_annual ────────────────────────────────────────────


class TestEffPenaltyAnnual:
    def test_no_step_up_config(self):
        resolver = _make_resolver()
        assert resolver.eff_penalty_annual(date(2026, 1, 1), None) == Decimal("4.20") * Decimal("1.5")

    def test_step_up_not_yet_triggered(self):
        resolver = _make_resolver(step_up_rate=Decimal("20"))
        first_penalty_start = date(2025, 1, 1)
        # 触发日前 89 天：未加码
        result = resolver.eff_penalty_annual(first_penalty_start + timedelta(days=89), first_penalty_start)
        assert result == Decimal("4.20") * Decimal("1.5")

    def test_step_up_triggered(self):
        resolver = _make_resolver(step_up_rate=Decimal("20"))
        first_penalty_start = date(2025, 1, 1)
        result = resolver.eff_penalty_annual(first_penalty_start + timedelta(days=90), first_penalty_start)
        base = Decimal("4.20") * Decimal("1.5")
        assert result == base * (Decimal("1") + Decimal("20") / Decimal("100"))

    def test_step_up_capped_after_multiplier(self):
        resolver = _make_resolver(step_up_rate=Decimal("20"), cap_penalty_annual=Decimal("7.0"))
        first_penalty_start = date(2025, 1, 1)
        result = resolver.eff_penalty_annual(first_penalty_start + timedelta(days=200), first_penalty_start)
        assert result == Decimal("7.0")

    def test_step_up_ignored_without_first_penalty_start(self):
        resolver = _make_resolver(step_up_rate=Decimal("20"))
        assert resolver.eff_penalty_annual(date(2026, 1, 1), None) == Decimal("4.20") * Decimal("1.5")
