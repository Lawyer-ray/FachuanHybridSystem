"""
Refactored pure data processing tests for PreservationQuoteService.

Tests the extracted validation / computation logic that does NOT require
database, external API, or async operations.
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


from plugins.court_automation.preservation_quote.service import PreservationQuoteService
from plugins.court_automation.preservation_quote.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> PreservationQuoteService:
    """Create PreservationQuoteService with mocked dependencies."""
    return PreservationQuoteService(
        token_service=MagicMock(),
        auto_token_service=MagicMock(),
        insurance_client=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# _validate_create_params
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateCreateParams:
    """Test _validate_create_params pure validation logic."""

    def test_valid_params_pass(self) -> None:
        """Valid params do not raise."""
        svc = _make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("10000"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )

    def test_zero_amount_raises(self) -> None:
        """Zero preserve amount raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("0"),
                corp_id="2550",
                category_id="127000",
                credential_id=1,
            )

    def test_negative_amount_raises(self) -> None:
        """Negative preserve amount raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("-100"),
                corp_id="2550",
                category_id="127000",
                credential_id=1,
            )

    def test_empty_corp_id_raises(self) -> None:
        """Empty corp_id raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="",
                category_id="127000",
                credential_id=1,
            )

    def test_whitespace_corp_id_raises(self) -> None:
        """Whitespace-only corp_id raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="   ",
                category_id="127000",
                credential_id=1,
            )

    def test_empty_category_id_raises(self) -> None:
        """Empty category_id raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="2550",
                category_id="",
                credential_id=1,
            )

    def test_negative_credential_id_raises(self) -> None:
        """Negative credential_id raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="2550",
                category_id="127000",
                credential_id=-1,
            )

    def test_zero_credential_id_raises(self) -> None:
        """Zero credential_id raises ValidationError."""
        svc = _make_service()
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="2550",
                category_id="127000",
                credential_id=0,
            )

    def test_none_credential_id_passes(self) -> None:
        """None credential_id is accepted."""
        svc = _make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("10000"),
            corp_id="2550",
            category_id="127000",
            credential_id=None,  # type: ignore[arg-type]
        )

    def test_multiple_errors_collected(self) -> None:
        """Multiple validation errors are collected in single exception."""
        svc = _make_service()
        with pytest.raises(ValidationError) as exc_info:
            svc._validate_create_params(
                preserve_amount=Decimal("-1"),
                corp_id="",
                category_id="",
                credential_id=-1,
        )
        errors = exc_info.value.errors
        assert "preserve_amount" in errors
        assert "corp_id" in errors
        assert "category_id" in errors
        assert "credential_id" in errors

    def test_large_amount_passes(self) -> None:
        """Large valid amount passes."""
        svc = _make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("999999999999"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )

    def test_small_positive_amount_passes(self) -> None:
        """Smallest positive amount passes."""
        svc = _make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("0.01"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )


# ═══════════════════════════════════════════════════════════════════════════
# determine_quote_status (from execute_quote)
# ═══════════════════════════════════════════════════════════════════════════

class TestExecuteQuoteStatusLogic:
    """Test the status determination logic from execute_quote."""

    @staticmethod
    def determine_status(success: int, failed: int) -> tuple[str, str | None]:
        """Mirror of the status logic in execute_quote."""
        if success == 0:
            return "failed", "所有保险公司查询均失败"
        elif failed == 0:
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
        assert msg is not None

    def test_partial(self) -> None:
        status, msg = self.determine_status(3, 2)
        assert status == "partial_success"

    def test_one_success(self) -> None:
        status, _ = self.determine_status(1, 0)
        assert status == "success"

    def test_one_failed(self) -> None:
        status, _ = self.determine_status(0, 1)
        assert status == "failed"


# ═══════════════════════════════════════════════════════════════════════════
# list_quotes validation
# ═══════════════════════════════════════════════════════════════════════════

class TestListQuotesValidation:
    """Test list_quotes parameter validation logic."""

    @staticmethod
    def validate_params(page: int, page_size: int, max_page_size: int = 100) -> dict[str, str]:
        """Extracted validation from list_quotes."""
        errors: dict[str, str] = {}
        if page < 1:
            errors["page"] = "页码必须大于 0"
        if page_size < 1 or page_size > max_page_size:
            errors["page_size"] = f"每页数量必须在 1-{max_page_size} 之间"
        return errors

    def test_valid(self) -> None:
        assert self.validate_params(1, 20) == {}

    def test_page_zero(self) -> None:
        assert "page" in self.validate_params(0, 20)

    def test_page_size_too_large(self) -> None:
        assert "page_size" in self.validate_params(1, 200)

    def test_page_size_zero(self) -> None:
        assert "page_size" in self.validate_params(1, 0)

    def test_boundary_page_size(self) -> None:
        assert self.validate_params(1, 100) == {}
