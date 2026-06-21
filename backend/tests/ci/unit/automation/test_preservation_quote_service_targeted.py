"""Targeted tests for PreservationQuoteService and QuoteExecutionMixin."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from django.utils import timezone

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus


# ── PreservationQuoteService ──────────────────────────────────────


@pytest.fixture
def quote_service():
    from plugins.court_automation.preservation_quote.service import PreservationQuoteService

    return PreservationQuoteService(
        token_service=MagicMock(),
        auto_token_service=MagicMock(),
        insurance_client=MagicMock(),
    )


@pytest.mark.django_db
class TestPreservationQuoteServiceCreate:
    def test_creates_quote(self, quote_service):
        quote = quote_service.create_quote(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
        )
        assert quote.pk is not None
        assert quote.status == QuoteStatus.PENDING
        assert quote.preserve_amount == Decimal("100000")

    def test_creates_with_credential(self, quote_service):
        quote = quote_service.create_quote(
            preserve_amount=Decimal("50000"),
            corp_id="1234",
            category_id="999",
            credential_id=42,
        )
        assert quote.credential_id == 42

    def test_negative_amount_raises(self, quote_service):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            quote_service.create_quote(
                preserve_amount=Decimal("-100"),
                corp_id="2550",
                category_id="127000",
            )

    def test_empty_corp_id_raises(self, quote_service):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            quote_service.create_quote(
                preserve_amount=Decimal("100000"),
                corp_id="",
                category_id="127000",
            )

    def test_empty_category_id_raises(self, quote_service):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            quote_service.create_quote(
                preserve_amount=Decimal("100000"),
                corp_id="2550",
                category_id="",
            )


@pytest.mark.django_db
class TestPreservationQuoteServiceGet:
    def test_get_quote(self, quote_service):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
        )
        result = quote_service.get_quote(quote.id)
        assert result.id == quote.id

    def test_get_not_found(self, quote_service):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            quote_service.get_quote(999999)


@pytest.mark.django_db
class TestPreservationQuoteServiceList:
    def test_list_quotes(self, quote_service):
        PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
        )
        quotes, total = quote_service.list_quotes(page=1, page_size=10)
        assert total >= 1
        assert len(quotes) >= 1

    def test_list_with_status_filter(self, quote_service):
        PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
            status=QuoteStatus.PENDING,
        )
        PreservationQuote.objects.create(
            preserve_amount=Decimal("200000"),
            corp_id="2550",
            category_id="127000",
            status=QuoteStatus.FAILED,
        )
        quotes, total = quote_service.list_quotes(page=1, page_size=10, status=QuoteStatus.PENDING)
        assert all(q.status == QuoteStatus.PENDING for q in quotes)

    def test_list_invalid_page(self, quote_service):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            quote_service.list_quotes(page=0)


@pytest.mark.django_db
class TestPreservationQuoteServiceExecute:
    def test_execute_not_found(self, quote_service):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            asyncio.run(quote_service.execute_quote(999999))


@pytest.mark.django_db
class TestPreservationQuoteServiceRetry:
    def test_retry_not_found(self, quote_service):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            asyncio.run(quote_service.retry_quote(999999))


# ── Validate create params ────────────────────────────────────────


class TestValidateCreateParams:
    def _make_service(self):
        from plugins.court_automation.preservation_quote.service import PreservationQuoteService

        return PreservationQuoteService()

    def test_valid_params(self):
        svc = self._make_service()
        svc._validate_create_params(Decimal("100000"), "2550", "127000", None)

    def test_negative_amount(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            svc._validate_create_params(Decimal("-1"), "2550", "127000", None)

    def test_empty_corp(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            svc._validate_create_params(Decimal("100"), "", "127000", None)

    def test_empty_category(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            svc._validate_create_params(Decimal("100"), "2550", "", None)

    def test_invalid_credential(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        with pytest.raises(ValidationError):
            svc._validate_create_params(Decimal("100"), "2550", "127000", -1)


import asyncio
