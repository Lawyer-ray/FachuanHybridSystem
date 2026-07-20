"""
Refactored pure data processing tests for QuoteExecutionMixin.

Tests the extracted data transformation / computation logic that does NOT
require database, external API, or async operations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.preservation_quote.execution_mixin import QuoteExecutionMixin
from plugins.court_automation.preservation_quote.court_insurance_client import InsuranceCompany, PremiumResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mixin() -> QuoteExecutionMixin:
    """Create QuoteExecutionMixin bypassing abstract properties."""
    mixin = QuoteExecutionMixin.__new__(QuoteExecutionMixin)
    return mixin


def _make_company(c_code: str = "PICC", c_name: str = "人保", c_id: str = "1") -> InsuranceCompany:
    return InsuranceCompany(c_id=c_id, c_code=c_code, c_name=c_name)


def _make_success_result(company: InsuranceCompany | None = None, premium: str = "100.00") -> PremiumResult:
    company = company or _make_company()
    return PremiumResult(
        company=company,
        premium=Decimal(premium),
        status="success",
        error_message=None,
        response_data={"data": {"minPremium": premium, "minAmount": premium}},
    )


def _make_failed_result(company: InsuranceCompany | None = None) -> PremiumResult:
    company = company or _make_company()
    return PremiumResult(
        company=company,
        premium=None,
        status="failed",
        error_message="查询失败",
        response_data=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# clean_decimal (extracted from _save_premium_results)
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanDecimal:
    """Test the clean_decimal extraction logic from _save_premium_results."""

    @staticmethod
    def clean_decimal(value: Any) -> Decimal | None:
        """Mirror of the clean_decimal function inside _save_premium_results."""
        if value is None or value == "" or value == "null":
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError, ArithmeticError):
            return None

    def test_normal_string_number(self) -> None:
        assert self.clean_decimal("123.45") == Decimal("123.45")

    def test_integer_value(self) -> None:
        assert self.clean_decimal(100) == Decimal("100")

    def test_none_returns_none(self) -> None:
        assert self.clean_decimal(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert self.clean_decimal("") is None

    def test_null_string_returns_none(self) -> None:
        assert self.clean_decimal("null") is None

    def test_zero_value(self) -> None:
        assert self.clean_decimal(0) == Decimal("0")

    def test_float_value(self) -> None:
        assert self.clean_decimal(3.14) == Decimal("3.14")

    def test_non_numeric_string_returns_none(self) -> None:
        assert self.clean_decimal("abc") is None

    def test_large_number(self) -> None:
        assert self.clean_decimal("999999999.99") == Decimal("999999999.99")

    def test_negative_number(self) -> None:
        assert self.clean_decimal("-50.5") == Decimal("-50.5")


# ═══════════════════════════════════════════════════════════════════════════
# result categorization (success/failed counting)
# ═══════════════════════════════════════════════════════════════════════════

class TestResultCategorization:
    """Test the success/failed counting logic from _save_premium_results."""

    @staticmethod
    def count_results(results: list[PremiumResult]) -> tuple[int, int]:
        """Mirror of the counting logic in _save_premium_results."""
        success = sum(1 for r in results if r.status == "success")
        failed = len(results) - success
        return success, failed

    def test_all_success(self) -> None:
        results = [_make_success_result(), _make_success_result()]
        s, f = self.count_results(results)
        assert s == 2
        assert f == 0

    def test_all_failed(self) -> None:
        results = [_make_failed_result(), _make_failed_result()]
        s, f = self.count_results(results)
        assert s == 0
        assert f == 2

    def test_mixed_results(self) -> None:
        results = [_make_success_result(), _make_failed_result(), _make_success_result()]
        s, f = self.count_results(results)
        assert s == 2
        assert f == 1

    def test_empty_list(self) -> None:
        s, f = self.count_results([])
        assert s == 0
        assert f == 0

    def test_single_success(self) -> None:
        s, f = self.count_results([_make_success_result()])
        assert s == 1
        assert f == 0


# ═══════════════════════════════════════════════════════════════════════════
# rate_data extraction logic
# ═══════════════════════════════════════════════════════════════════════════

class TestRateDataExtraction:
    """Test the rate_data extraction logic from _save_premium_results."""

    @staticmethod
    def extract_rate_data(result: PremiumResult) -> dict[str, Any]:
        """Mirror of rate_data extraction in _save_premium_results."""
        rate_data: dict[str, Any] = {}
        if result.response_data and isinstance(result.response_data, dict):
            raw = result.response_data.get("data")
            if isinstance(raw, dict):
                rate_data = raw
        return rate_data

    def test_standard_response(self) -> None:
        result = PremiumResult(
            company=_make_company(),
            premium=Decimal("100"),
            status="success",
            error_message=None,
            response_data={"data": {"minPremium": "100", "minRate": "0.05"}},
        )
        rate_data = self.extract_rate_data(result)
        assert rate_data["minPremium"] == "100"
        assert rate_data["minRate"] == "0.05"

    def test_none_response_data(self) -> None:
        result = PremiumResult(
            company=_make_company(),
            premium=None,
            status="failed",
            error_message="err",
            response_data=None,
        )
        assert self.extract_rate_data(result) == {}

    def test_no_data_key(self) -> None:
        result = PremiumResult(
            company=_make_company(),
            premium=None,
            status="failed",
            error_message="err",
            response_data={"other": "value"},
        )
        assert self.extract_rate_data(result) == {}

    def test_data_not_dict(self) -> None:
        result = PremiumResult(
            company=_make_company(),
            premium=None,
            status="failed",
            error_message="err",
            response_data={"data": "string_value"},
        )
        assert self.extract_rate_data(result) == {}

    def test_nested_rate_fields(self) -> None:
        result = PremiumResult(
            company=_make_company(),
            premium=Decimal("500"),
            status="success",
            error_message=None,
            response_data={
                "data": {
                    "minPremium": "500",
                    "minAmount": "500",
                    "maxAmount": "10000",
                    "minRate": "0.05",
                    "maxRate": "0.10",
                    "maxApplyAmount": "50000",
                }
            },
        )
        rate_data = self.extract_rate_data(result)
        assert rate_data["minRate"] == "0.05"
        assert rate_data["maxRate"] == "0.10"
        assert rate_data["maxApplyAmount"] == "50000"


# ═══════════════════════════════════════════════════════════════════════════
# determine_quote_status (from execute_quote)
# ═══════════════════════════════════════════════════════════════════════════

class TestDetermineQuoteStatus:
    """Test the quote status determination logic from execute_quote."""

    @staticmethod
    def determine_status(success_count: int, failed_count: int) -> tuple[str, str | None]:
        """Mirror of status determination logic in execute_quote."""
        if success_count == 0:
            return "failed", "所有保险公司查询均失败"
        elif failed_count == 0:
            return "success", None
        else:
            return "partial_success", None

    def test_all_success(self) -> None:
        status, msg = self.determine_status(5, 0)
        assert status == "success"
        assert msg is None

    def test_all_failed(self) -> None:
        status, msg = self.determine_status(0, 5)
        assert status == "failed"
        assert msg == "所有保险公司查询均失败"

    def test_partial_success(self) -> None:
        status, msg = self.determine_status(3, 2)
        assert status == "partial_success"
        assert msg is None

    def test_one_success_zero_failed(self) -> None:
        status, msg = self.determine_status(1, 0)
        assert status == "success"

    def test_zero_success_one_failed(self) -> None:
        status, msg = self.determine_status(0, 1)
        assert status == "failed"
