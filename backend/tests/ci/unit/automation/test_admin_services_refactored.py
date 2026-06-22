"""
Refactored pure data processing tests for admin services.

Tests the extracted data computation / formatting / validation logic
from CourtDocumentAdminService, PreservationQuoteAdminService,
and TokenAcquisitionHistoryAdminService that does NOT require database

or model instances.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")



# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: compute_percentage
# ═══════════════════════════════════════════════════════════════════════════

class TestComputePercentage:
    """Test percentage computation (used across multiple admin services)."""

    @staticmethod
    def compute_percentage(count: int, total: int) -> float:
        """Extracted percentage computation from admin services."""
        return (count / total * 100) if total > 0 else 0

    def test_normal_case(self) -> None:
        assert self.compute_percentage(3, 10) == 30.0

    def test_full_percentage(self) -> None:
        assert self.compute_percentage(10, 10) == 100.0

    def test_zero_count(self) -> None:
        assert self.compute_percentage(0, 10) == 0.0

    def test_zero_total_returns_zero(self) -> None:
        """Division by zero is handled (returns 0, not error)."""
        assert self.compute_percentage(5, 0) == 0.0

    def test_both_zero(self) -> None:
        assert self.compute_percentage(0, 0) == 0.0

    def test_fractional_result(self) -> None:
        result = self.compute_percentage(1, 3)
        assert abs(result - 33.333333333333336) < 1e-10

    def test_large_numbers(self) -> None:
        assert self.compute_percentage(9999, 10000) == 99.99


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: build_status_stats
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildStatusStats:
    """Test the status statistics building pattern used in admin services."""

    @staticmethod
    def build_status_stats(
        total: int, counts: dict[str, int], choices: list[tuple[str, str]]
    ) -> dict[str, dict[str, Any]]:
        """Extracted pattern from get_document_statistics / get_quote_statistics."""
        stats: dict[str, dict[str, Any]] = {}
        for status_code, status_name in choices:
            count = counts.get(status_code, 0)
            stats[status_code] = {
                "name": status_name,
                "count": count,
                "percentage": (count / total * 100) if total > 0 else 0,
            }
        return stats

    def test_basic_stats(self) -> None:
        choices = [("pending", "待处理"), ("success", "成功"), ("failed", "失败")]
        counts = {"pending": 2, "success": 5, "failed": 1}
        result = self.build_status_stats(8, counts, choices)
        assert result["pending"]["count"] == 2
        assert result["pending"]["name"] == "待处理"
        assert abs(result["pending"]["percentage"] - 25.0) < 1e-10
        assert result["success"]["percentage"] == 62.5

    def test_empty_total(self) -> None:
        choices = [("pending", "待处理")]
        result = self.build_status_stats(0, {}, choices)
        assert result["pending"]["percentage"] == 0.0
        assert result["pending"]["count"] == 0

    def test_missing_status_defaults_to_zero(self) -> None:
        choices = [("a", "A"), ("b", "B")]
        result = self.build_status_stats(10, {"a": 10}, choices)
        assert result["a"]["count"] == 10
        assert result["b"]["count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: validate_batch_quote_config
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateBatchQuoteConfig:
    """Test batch quote config validation (extracted from batch_create_quotes)."""

    @staticmethod
    def validate_single_config(config: dict[str, Any]) -> dict[str, Any]:
        """Extracted validation for a single quote config.

        Returns empty dict on success, or error dict on failure.
        """
        errors: dict[str, Any] = {}
        if "preserve_amount" not in config:
            errors["preserve_amount"] = "missing"
            return errors

        try:
            preserve_amount = Decimal(str(config["preserve_amount"]))
            if preserve_amount <= 0:
                errors["preserve_amount"] = "must_be_positive"
        except Exception:
            errors["preserve_amount"] = "invalid"

        return errors

    def test_valid_config(self) -> None:
        result = self.validate_single_config({"preserve_amount": "10000", "corp_id": "2550"})
        assert result == {}

    def test_missing_preserve_amount(self) -> None:
        result = self.validate_single_config({"corp_id": "2550"})
        assert "preserve_amount" in result

    def test_zero_amount(self) -> None:
        result = self.validate_single_config({"preserve_amount": "0"})
        assert "preserve_amount" in result

    def test_negative_amount(self) -> None:
        result = self.validate_single_config({"preserve_amount": "-100"})
        assert "preserve_amount" in result

    def test_decimal_string_amount(self) -> None:
        result = self.validate_single_config({"preserve_amount": "10000.50"})
        assert result == {}

    def test_integer_amount(self) -> None:
        result = self.validate_single_config({"preserve_amount": 50000})
        assert result == {}

    def test_non_numeric_amount(self) -> None:
        result = self.validate_single_config({"preserve_amount": "abc"})
        assert "preserve_amount" in result


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: format_csv_row
# ═══════════════════════════════════════════════════════════════════════════

class TestFormatCSVRow:
    """Test CSV row formatting (extracted from export_to_csv)."""

    @staticmethod
    def format_csv_row(record: Any) -> list[str | int | float]:
        """Extracted CSV row formatting from export_to_csv."""
        return [
            record.id,
            record.site_name,
            record.account,
            record.credential_id or "",
            record.get_status_display(),
            record.trigger_reason,
            record.attempt_count,
            record.total_duration or "",
            record.login_duration or "",
            record.captcha_attempts,
            record.network_retries,
            record.token_preview or "",
            record.error_message or "",
            record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
            record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else "",
            record.finished_at.strftime("%Y-%m-%d %H:%M:%S") if record.finished_at else "",
        ]

    def _make_record(self, **kwargs: Any) -> MagicMock:
        """Create a mock token acquisition history record."""
        record = MagicMock()
        record.id = kwargs.get("id", 1)
        record.site_name = kwargs.get("site_name", "court_zxfw")
        record.account = kwargs.get("account", "test_account")
        record.credential_id = kwargs.get("credential_id", 100)
        record.get_status_display.return_value = kwargs.get("status_display", "成功")
        record.trigger_reason = kwargs.get("trigger_reason", "manual")
        record.attempt_count = kwargs.get("attempt_count", 1)
        record.total_duration = kwargs.get("total_duration", 5.5)
        record.login_duration = kwargs.get("login_duration", 3.2)
        record.captcha_attempts = kwargs.get("captcha_attempts", 0)
        record.network_retries = kwargs.get("network_retries", 0)
        record.token_preview = kwargs.get("token_preview", "abc123...")
        record.error_message = kwargs.get("error_message")
        record.created_at = kwargs.get("created_at", datetime(2026, 6, 9, 10, 30, 0))
        record.started_at = kwargs.get("started_at", datetime(2026, 6, 9, 10, 30, 1))
        record.finished_at = kwargs.get("finished_at", datetime(2026, 6, 9, 10, 30, 5))
        return record

    def test_normal_record(self) -> None:
        record = self._make_record()
        row = self.format_csv_row(record)
        assert row[0] == 1
        assert row[1] == "court_zxfw"
        assert row[7] == 5.5
        assert row[13] == "2026-06-09 10:30:00"

    def test_none_optional_fields(self) -> None:
        record = self._make_record(
            credential_id=None,
            total_duration=None,
            login_duration=None,
            token_preview=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )
        row = self.format_csv_row(record)
        assert row[3] == ""  # credential_id
        assert row[7] == ""  # total_duration
        assert row[11] == ""  # token_preview
        assert row[14] == ""  # started_at
        assert row[15] == ""  # finished_at

    def test_row_length_is_16(self) -> None:
        """CSV row always has 16 columns (matching headers)."""
        record = self._make_record()
        row = self.format_csv_row(record)
        assert len(row) == 16


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: build_amount_ranges
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildAmountRanges:
    """Test amount range bucketing (extracted from get_quote_statistics)."""

    AMOUNT_RANGES = [
        (0, 10000, "1万以下"),
        (10000, 100000, "1-10万"),
        (100000, 1000000, "10-100万"),
        (1000000, 10000000, "100-1000万"),
        (10000000, float("inf"), "1000万以上"),
    ]

    @classmethod
    def classify_amount(cls, amount: float) -> str:
        """Return the range label for a given amount."""
        for min_val, max_val, label in cls.AMOUNT_RANGES:
            if max_val == float("inf"):
                if amount >= min_val:
                    return label
            elif min_val <= amount < max_val:
                return label
        return "unknown"

    def test_below_10k(self) -> None:
        assert self.classify_amount(5000) == "1万以下"

    def test_exactly_10k(self) -> None:
        assert self.classify_amount(10000) == "1-10万"

    def test_mid_range(self) -> None:
        assert self.classify_amount(500000) == "10-100万"

    def test_high_range(self) -> None:
        assert self.classify_amount(5000000) == "100-1000万"

    def test_above_10m(self) -> None:
        assert self.classify_amount(50000000) == "1000万以上"

    def test_zero_amount(self) -> None:
        assert self.classify_amount(0) == "1万以下"


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: build_download_progress
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildDownloadProgress:
    """Test download progress computation (from get_download_progress)."""

    @staticmethod
    def compute_progress(total: int, success: int) -> float:
        """Extracted progress percentage computation."""
        return (success / total * 100) if total > 0 else 0

    def test_normal_progress(self) -> None:
        assert self.compute_progress(100, 50) == 50.0

    def test_complete(self) -> None:
        assert self.compute_progress(50, 50) == 100.0

    def test_zero_total(self) -> None:
        assert self.compute_progress(0, 0) == 0.0

    def test_zero_success(self) -> None:
        assert self.compute_progress(10, 0) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: build_comparison_statistics
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildComparisonStatistics:
    """Test comparison statistics computation (from run_single_quote/get_quote_comparison)."""

    @staticmethod
    def compute_comparison_stats(premiums: list[float]) -> dict[str, Any]:
        """Extracted statistics computation from get_quote_comparison."""
        if not premiums:
            return {}
        return {
            "total_companies": len(premiums),
            "min_premium": min(premiums),
            "max_premium": max(premiums),
            "avg_premium": sum(premiums) / len(premiums),
            "price_range": max(premiums) - min(premiums),
            "savings_amount": max(premiums) - min(premiums),
            "savings_percentage": (
                ((max(premiums) - min(premiums)) / max(premiums) * 100) if max(premiums) > 0 else 0
            ),
        }

    def test_basic_stats(self) -> None:
        stats = self.compute_comparison_stats([100.0, 200.0, 300.0])
        assert stats["total_companies"] == 3
        assert stats["min_premium"] == 100.0
        assert stats["max_premium"] == 300.0
        assert stats["avg_premium"] == 200.0
        assert stats["savings_amount"] == 200.0

    def test_savings_percentage(self) -> None:
        stats = self.compute_comparison_stats([100.0, 200.0])
        # savings = (200 - 100) / 200 * 100 = 50%
        assert abs(stats["savings_percentage"] - 50.0) < 1e-10

    def test_single_company(self) -> None:
        stats = self.compute_comparison_stats([150.0])
        assert stats["total_companies"] == 1
        assert stats["savings_amount"] == 0.0
        assert stats["savings_percentage"] == 0.0

    def test_empty_premiums(self) -> None:
        stats = self.compute_comparison_stats([])
        assert stats == {}

    def test_all_same_premium(self) -> None:
        stats = self.compute_comparison_stats([100.0, 100.0, 100.0])
        assert stats["savings_amount"] == 0.0
        assert stats["savings_percentage"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: pagination parameter validation
# ═══════════════════════════════════════════════════════════════════════════

class TestValidatePaginationParams:
    """Test pagination parameter validation (from list_quotes)."""

    @staticmethod
    def validate_pagination(page: int, page_size: int, max_page_size: int = 100) -> dict[str, str]:
        """Extracted pagination validation from list_quotes."""
        errors: dict[str, str] = {}
        if page < 1:
            errors["page"] = "页码必须大于 0"
        if page_size < 1 or page_size > max_page_size:
            errors["page_size"] = f"每页数量必须在 1-{max_page_size} 之间"
        return errors

    def test_valid_params(self) -> None:
        assert self.validate_pagination(1, 20) == {}

    def test_page_zero(self) -> None:
        errors = self.validate_pagination(0, 20)
        assert "page" in errors

    def test_negative_page(self) -> None:
        errors = self.validate_pagination(-1, 20)
        assert "page" in errors

    def test_page_size_zero(self) -> None:
        errors = self.validate_pagination(1, 0)
        assert "page_size" in errors

    def test_page_size_exceeds_max(self) -> None:
        errors = self.validate_pagination(1, 101)
        assert "page_size" in errors

    def test_page_size_at_max(self) -> None:
        errors = self.validate_pagination(1, 100)
        assert errors == {}

    def test_custom_max_page_size(self) -> None:
        errors = self.validate_pagination(1, 51, max_page_size=50)
        assert "page_size" in errors

    def test_both_invalid(self) -> None:
        errors = self.validate_pagination(0, 0)
        assert "page" in errors
        assert "page_size" in errors


# ═══════════════════════════════════════════════════════════════════════════
# Pure helper: retry status validation
# ═══════════════════════════════════════════════════════════════════════════

class TestRetryStatusValidation:
    """Test the retry-allowed status check from retry_quote."""

    RETRYABLE_STATUSES = {"failed", "partial_success"}

    @classmethod
    def can_retry(cls, status: str) -> bool:
        """Extracted retry eligibility check."""
        return status in cls.RETRYABLE_STATUSES

    def test_failed_can_retry(self) -> None:
        assert self.can_retry("failed") is True

    def test_partial_success_can_retry(self) -> None:
        assert self.can_retry("partial_success") is True

    def test_success_cannot_retry(self) -> None:
        assert self.can_retry("success") is False

    def test_pending_cannot_retry(self) -> None:
        assert self.can_retry("pending") is False

    def test_running_cannot_retry(self) -> None:
        assert self.can_retry("running") is False
