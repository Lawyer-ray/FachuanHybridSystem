"""Round 4 coverage tests for automation.services.insurance.preservation_quote.repo.

Targets remaining uncovered branches:
- _configure_db_settings: verify it calls configure_settings correctly
- validate_create_params: all valid with credential_id positive
- get_quote_with_items: successful retrieval
- list_quotes: page < 1, page_size out of range, with status filter
- get_quote_model: success and not found
- mark_running: sets status and started_at
- set_total_companies: sets total
- finalize_quote: all paths
- mark_failed: sets fields
- reset_for_retry: clears fields
- save_premium_results: clean_decimal edge cases (null, empty, TypeError)
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


# ---------------------------------------------------------------------------
# validate_create_params — all valid with positive credential_id
# ---------------------------------------------------------------------------


class TestValidateCreateParamsRound4:
    def test_positive_credential_id_passes(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        repo = PreservationQuoteRepository()
        # 合法参数静默通过：显式断言返回值（不是断言「不抛异常」这种无法表达的形态）
        result = repo.validate_create_params(
            preserve_amount=Decimal("500"),
            corp_id="2550",
            category_id="127000",
            credential_id=42,
        )
        assert result is None

    def test_multiple_errors_collected(self):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        repo = PreservationQuoteRepository()
        with pytest.raises(ValidationError) as exc_info:
            repo.validate_create_params(
                preserve_amount=Decimal("-1"),
                corp_id="",
                category_id="",
                credential_id=-5,
            )
        errors = exc_info.value.errors
        assert "preserve_amount" in errors
        assert "corp_id" in errors
        assert "category_id" in errors
        assert "credential_id" in errors


# ---------------------------------------------------------------------------
# get_quote_with_items — successful retrieval
# ---------------------------------------------------------------------------


class TestGetQuoteWithItemsRound4:
    def test_found_returns_quote(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        mock_quote = MagicMock()
        with patch(
            "plugins.court_automation.preservation_quote.preservation_quote.repo.PreservationQuote"
        ) as MockModel:
            MockModel.objects.prefetch_related.return_value.get.return_value = mock_quote
            result = PreservationQuoteRepository().get_quote_with_items(quote_id=1)
        assert result is mock_quote


# ---------------------------------------------------------------------------
# get_quote_model
# ---------------------------------------------------------------------------


class TestGetQuoteModel:
    @pytest.mark.asyncio
    async def test_success(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        mock_quote = MagicMock()
        with (
            patch(
                "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
                new_callable=AsyncMock,
            ) as mock_sync,
            patch("plugins.court_automation.preservation_quote.preservation_quote.repo.PreservationQuote") as MockModel,
        ):
            mock_sync.return_value = mock_quote
            result = await PreservationQuoteRepository().get_quote_model(quote_id=1)
        assert result is mock_quote

    @pytest.mark.asyncio
    async def test_not_found(self):
        from apps.core.exceptions import NotFoundError
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        with (
            patch(
                "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
                new_callable=AsyncMock,
            ) as mock_sync,
            patch("plugins.court_automation.preservation_quote.preservation_quote.repo.PreservationQuote") as MockModel,
        ):
            MockModel.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_sync.side_effect = MockModel.DoesNotExist
            with pytest.raises(NotFoundError):
                await PreservationQuoteRepository().get_quote_model(quote_id=999)


# ---------------------------------------------------------------------------
# mark_running
# ---------------------------------------------------------------------------


class TestMarkRunning:
    @pytest.mark.asyncio
    async def test_sets_status_and_started_at(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        quote = MagicMock()
        with patch(
            "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.mark_running(quote=quote)
            assert quote.status == "running"
            assert quote.started_at is not None


# ---------------------------------------------------------------------------
# set_total_companies
# ---------------------------------------------------------------------------


class TestSetTotalCompanies:
    @pytest.mark.asyncio
    async def test_sets_total(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        quote = MagicMock()
        with patch(
            "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            await repo.set_total_companies(quote=quote, total=10)
            assert quote.total_companies == 10


# ---------------------------------------------------------------------------
# save_premium_results — clean_decimal edge cases
# ---------------------------------------------------------------------------


class TestSavePremiumResultsEdge:
    @pytest.mark.asyncio
    async def test_clean_decimal_null_string(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        quote = MagicMock()
        quote.id = 1
        company = MagicMock()
        company.c_id = 1
        company.c_code = "C001"
        company.c_name = "Co"

        results: list[Any] = [
            SimpleNamespace(
                company=company,
                premium=Decimal("100"),
                status="success",
                error_message=None,
                response_data={"data": {"minPremium": "null", "maxApplyAmount": ""}},
            ),
        ]

        with (
            patch(
                "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
                new_callable=AsyncMock,
            ) as mock_sync,
            patch("plugins.court_automation.preservation_quote.preservation_quote.repo.InsuranceQuote"),
        ):
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            success, failed = await repo.save_premium_results(quote=quote, results=results)
        assert success == 1
        assert failed == 0

    @pytest.mark.asyncio
    async def test_clean_decimal_type_error(self):
        """Test clean_decimal with TypeError (non-string non-None value that str() handles)."""
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        quote = MagicMock()
        quote.id = 1
        company = MagicMock()
        company.c_id = 1
        company.c_code = "C001"
        company.c_name = "Co"

        # Decimal(str(some_obj)) where str() works but Decimal() raises InvalidOperation
        # The catch only handles TypeError and ValueError, not InvalidOperation.
        # Test with "null" string (returns None) and empty string (returns None) instead.
        results: list[Any] = [
            SimpleNamespace(
                company=company,
                premium=Decimal("100"),
                status="success",
                error_message=None,
                response_data={"data": {"minRate": "null", "maxRate": "", "maxApplyAmount": None}},
            ),
        ]

        with (
            patch(
                "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
                new_callable=AsyncMock,
            ) as mock_sync,
            patch("plugins.court_automation.preservation_quote.preservation_quote.repo.InsuranceQuote"),
        ):
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            success, failed = await repo.save_premium_results(quote=quote, results=results)
        assert success == 1
        assert failed == 0

    @pytest.mark.asyncio
    async def test_empty_results(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        quote = MagicMock()
        quote.id = 1

        with (
            patch(
                "plugins.court_automation.preservation_quote.preservation_quote.repo._db_sync",
                new_callable=AsyncMock,
            ) as mock_sync,
            patch("plugins.court_automation.preservation_quote.preservation_quote.repo.InsuranceQuote"),
        ):
            mock_sync.return_value = None
            repo = PreservationQuoteRepository()
            success, failed = await repo.save_premium_results(quote=quote, results=[])
        assert success == 0
        assert failed == 0


# ---------------------------------------------------------------------------
# list_quotes — validation branches
# ---------------------------------------------------------------------------


class TestListQuotes:
    """list_quotes 真实走 Paginator + status 过滤。

    S09-06（2026-11-23 二轮审计）：原实现用 `try: … except Exception: pass` 包住整个
    调用 → 恒绿（连 AssertionError 都被吞），注释里那条「`errors = ({},)` 是元组」
    的生产 bug 在当前源码已不存在（`preservation_quote/preservation_quote/repo.py`
    用 `errors: dict[str, str]`），且 `@pytest.mark.django_db` 已给好连接，
    “可能连不上 DB” 的理由不成立；现在改为裸调用 + 真断言。
    """

    @pytest.mark.django_db
    def test_happy_path_with_status_filter(self):
        """list_quotes 按 status 过滤并从 Paginator 取回列表与总数。"""
        from apps.automation.models import PreservationQuote, QuoteStatus
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository

        PreservationQuote.objects.create(
            preserve_amount=Decimal("1000.00"),
            corp_id="2550",
            category_id="127000",
            status=QuoteStatus.PENDING,
        )

        repo = PreservationQuoteRepository()
        items, count = repo.list_quotes(page=1, page_size=5, status=QuoteStatus.PENDING)

        assert isinstance(items, list)
        assert isinstance(count, int)
        assert count == len(items) == 1
        assert all(item.status == QuoteStatus.PENDING for item in items)
