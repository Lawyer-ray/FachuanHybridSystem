"""Tests for sales_dispute.services.generation.dashboard_models utility functions."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.sales_dispute.services.generation.dashboard_models import (
    AMOUNT_RANGES,
    DEBT_AGE_RANGES,
    _amount_range_q,
    _lawyer_display_name,
    _safe_rate,
)


class TestSafeRate:
    def test_normal(self) -> None:
        result = _safe_rate(Decimal("50"), Decimal("100"))
        assert result == Decimal("50.00")

    def test_zero_denominator(self) -> None:
        result = _safe_rate(Decimal("50"), Decimal("0"))
        assert result == Decimal("0.00")

    def test_zero_numerator(self) -> None:
        result = _safe_rate(Decimal("0"), Decimal("100"))
        assert result == Decimal("0.00")

    def test_decimal_precision(self) -> None:
        result = _safe_rate(Decimal("1"), Decimal("3"))
        assert result == Decimal("33.33")

    def test_large_numbers(self) -> None:
        result = _safe_rate(Decimal("1000000"), Decimal("3000000"))
        assert result == Decimal("33.33")


class TestAmountRangeQ:
    def test_both_bounds(self) -> None:
        q = _amount_range_q("amount", Decimal("100"), Decimal("500"))
        assert q is not None

    def test_low_only(self) -> None:
        q = _amount_range_q("amount", Decimal("100"), None)
        assert q is not None

    def test_high_only(self) -> None:
        q = _amount_range_q("amount", None, Decimal("500"))
        assert q is not None

    def test_neither(self) -> None:
        q = _amount_range_q("amount", None, None)
        # Empty Q object
        assert q is not None


class TestLawyerDisplayName:
    def test_none(self) -> None:
        assert _lawyer_display_name(None) == "未知律师"

    def test_real_name(self) -> None:
        lawyer = MagicMock()
        lawyer.real_name = "张三"
        assert _lawyer_display_name(lawyer) == "张三"

    def test_username_fallback(self) -> None:
        lawyer = MagicMock()
        lawyer.real_name = None
        lawyer.username = "zhangsan"
        assert _lawyer_display_name(lawyer) == "zhangsan"

    def test_empty_real_name(self) -> None:
        lawyer = MagicMock()
        lawyer.real_name = ""
        lawyer.username = "zhangsan"
        assert _lawyer_display_name(lawyer) == "zhangsan"

    def test_all_empty(self) -> None:
        lawyer = MagicMock()
        lawyer.real_name = None
        lawyer.username = ""
        assert _lawyer_display_name(lawyer) == "未知律师"


class TestConstants:
    def test_amount_ranges_count(self) -> None:
        assert len(AMOUNT_RANGES) == 4

    def test_debt_age_ranges_count(self) -> None:
        assert len(DEBT_AGE_RANGES) == 3

    def test_amount_ranges_structure(self) -> None:
        for label, low, high in AMOUNT_RANGES:
            assert isinstance(label, str)
            assert low is None or isinstance(low, Decimal)
            assert high is None or isinstance(high, Decimal)

    def test_debt_age_ranges_structure(self) -> None:
        for label, low, high in DEBT_AGE_RANGES:
            assert isinstance(label, str)
            assert low is None or isinstance(low, int)
            assert high is None or isinstance(high, int)
