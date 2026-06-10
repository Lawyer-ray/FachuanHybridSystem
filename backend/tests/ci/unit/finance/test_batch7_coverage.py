"""Batch7 coverage tests for apps.finance."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.finance.models.lpr_rate import LPRRate


# ── LPRRate ─────────────────────────────────────────────────────────────────


class TestLPRRate:
    def test_str_method(self) -> None:
        rate = LPRRate.__new__(LPRRate)
        rate.effective_date = "2025-01-20"
        rate.rate_1y = Decimal("3.10")
        rate.rate_5y = Decimal("3.60")
        result = str(rate)
        assert "2025-01-20" in result
        assert "3.10" in result
        assert "3.60" in result

    def test_rate_1y_decimal(self) -> None:
        rate = LPRRate.__new__(LPRRate)
        rate.rate_1y = Decimal("3.45")
        assert rate.rate_1y_decimal == Decimal("0.0345")

    def test_rate_5y_decimal(self) -> None:
        rate = LPRRate.__new__(LPRRate)
        rate.rate_5y = Decimal("3.95")
        assert rate.rate_5y_decimal == Decimal("0.0395")

    def test_rate_1y_decimal_zero(self) -> None:
        rate = LPRRate.__new__(LPRRate)
        rate.rate_1y = Decimal("0.00")
        assert rate.rate_1y_decimal == Decimal("0.0000")

    def test_meta_ordering(self) -> None:
        assert LPRRate._meta.ordering == ["-effective_date"]

    def test_meta_verbose_name(self) -> None:
        assert LPRRate._meta.verbose_name == "LPR利率"
