"""Tests for automation.services.insurance.preservation_quote.repo.

Covers: validate_create_params, get_quote_with_items, finalize_quote,
mark_failed, reset_for_retry, save_premium_results clean_decimal.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# validate_create_params
# ---------------------------------------------------------------------------


class TestValidateCreateParams:
    def _repo(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )
        return PreservationQuoteRepository()

    def test_all_valid(self):
        self._repo().validate_create_params(
            preserve_amount=Decimal("1000"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )

    def test_negative_amount(self):
        from apps.automation.services.insurance.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self._repo().validate_create_params(
                preserve_amount=Decimal("-1"),
                corp_id="2550",
                category_id="127000",
                credential_id=None,
            )

    def test_zero_amount(self):
        from apps.automation.services.insurance.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self._repo().validate_create_params(
                preserve_amount=Decimal("0"),
                corp_id="2550",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_corp_id(self):
        from apps.automation.services.insurance.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self._repo().validate_create_params(
                preserve_amount=Decimal("100"),
                corp_id="",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_category_id(self):
        from apps.automation.services.insurance.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self._repo().validate_create_params(
                preserve_amount=Decimal("100"),
                corp_id="2550",
                category_id="  ",
                credential_id=None,
            )

    def test_invalid_credential_id(self):
        from apps.automation.services.insurance.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self._repo().validate_create_params(
                preserve_amount=Decimal("100"),
                corp_id="2550",
                category_id="127000",
                credential_id=-1,
            )

    def test_none_credential_id_ok(self):
        self._repo().validate_create_params(
            preserve_amount=Decimal("100"),
            corp_id="2550",
            category_id="127000",
            credential_id=None,
        )


# ---------------------------------------------------------------------------
# get_quote_with_items
# ---------------------------------------------------------------------------


class TestGetQuoteWithItems:
    @pytest.mark.django_db
    def test_not_found_raises(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )
        from apps.core.exceptions import NotFoundError

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo.PreservationQuote"
        ) as MockModel:
            MockModel.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockModel.objects.prefetch_related.return_value.get.side_effect = MockModel.DoesNotExist
            with pytest.raises(NotFoundError):
                PreservationQuoteRepository().get_quote_with_items(quote_id=999)


# ---------------------------------------------------------------------------
# finalize_quote
# ---------------------------------------------------------------------------


class TestFinalizeQuote:
    @pytest.mark.asyncio
    async def test_all_success(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.finalize_quote(
                quote=quote, success_count=5, failed_count=0, error_message=None
            )
            assert quote.status == "success"  # QuoteStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_all_failed(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.finalize_quote(
                quote=quote, success_count=0, failed_count=3, error_message="all fail"
            )
            assert quote.error_message == "all fail"

    @pytest.mark.asyncio
    async def test_all_failed_no_error_message(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.finalize_quote(
                quote=quote, success_count=0, failed_count=3, error_message=None
            )
            assert quote.error_message == "所有保险公司查询均失败"

    @pytest.mark.asyncio
    async def test_partial_success(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.finalize_quote(
                quote=quote, success_count=3, failed_count=2, error_message=None
            )
            # partial_success status
            assert quote.success_count == 3
            assert quote.failed_count == 2


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_sets_status(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.mark_failed(quote=quote, error_message="timeout")
            assert quote.error_message == "timeout"


# ---------------------------------------------------------------------------
# reset_for_retry
# ---------------------------------------------------------------------------


class TestResetForRetry:
    @pytest.mark.asyncio
    async def test_resets_fields(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.save = AsyncMock()

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.reset_for_retry(quote=quote)
            assert quote.status == "pending"  # QuoteStatus.PENDING
            assert quote.error_message is None
            assert quote.started_at is None
            assert quote.finished_at is None


# ---------------------------------------------------------------------------
# save_premium_results — clean_decimal
# ---------------------------------------------------------------------------


class TestSavePremiumResultsCleanDecimal:
    @pytest.mark.asyncio
    async def test_clean_decimal_none_and_empty(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.id = 1

        company = MagicMock()
        company.c_id = 1
        company.c_code = "C001"
        company.c_name = "Test Co"

        results = [
            SimpleNamespace(
                company=company,
                premium=Decimal("100"),
                status="success",
                error_message=None,
                response_data={"data": {"minPremium": None, "minAmount": "", "maxAmount": "null", "minRate": "0.5", "maxRate": 1000}},
            ),
            SimpleNamespace(
                company=company,
                premium=None,
                status="failed",
                error_message="err",
                response_data=None,
            ),
        ]

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync, patch(
            "apps.automation.services.insurance.preservation_quote.repo.InsuranceQuote"
        ) as MockIQ:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            success, failed = await repo.save_premium_results(quote=quote, results=results)
            assert success == 1
            assert failed == 1

    @pytest.mark.asyncio
    async def test_non_dict_response_data(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        quote = MagicMock()
        quote.id = 1

        company = MagicMock()
        company.c_id = 1
        company.c_code = "C001"
        company.c_name = "Test Co"

        results = [
            SimpleNamespace(
                company=company,
                premium=Decimal("100"),
                status="success",
                error_message=None,
                response_data={"data": "not_a_dict"},
            ),
        ]

        with patch(
            "apps.automation.services.insurance.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync, patch(
            "apps.automation.services.insurance.preservation_quote.repo.InsuranceQuote"
        ) as MockIQ:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            success, failed = await repo.save_premium_results(quote=quote, results=results)
            assert success == 1
            assert failed == 0


# ---------------------------------------------------------------------------
# _configure_db_settings
# ---------------------------------------------------------------------------


class TestConfigureDbSettings:
    def test_calls_configure(self):
        from apps.automation.services.insurance.preservation_quote.repo import (
            _configure_db_settings,
        )

        with patch("apps.automation.services.insurance.preservation_quote.repo.connections") as mock_conn:
            mock_conn._settings = "raw"
            mock_conn.configure_settings.return_value = "configured"
            _configure_db_settings()
            mock_conn.configure_settings.assert_called_once_with("raw")
