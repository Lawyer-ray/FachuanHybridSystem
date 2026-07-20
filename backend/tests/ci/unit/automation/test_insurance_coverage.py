"""Coverage tests for automation.services.insurance.exceptions, automation.services.insurance._insurance_http_mixin, automation.services.insurance.preservation_quote.token_provider."""
from __future__ import annotations

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal


class TestInsuranceExceptions:
    def test_preservation_quote_error(self):
        from plugins.court_automation.preservation_quote.exceptions import PreservationQuoteError
        err = PreservationQuoteError("test error")
        assert err.message == "test error"
        assert err.code == "PRESERVATION_QUOTE_ERROR"

    def test_token_error(self):
        from plugins.court_automation.preservation_quote.exceptions import TokenError
        err = TokenError("token expired")
        assert err.code == "TOKEN_ERROR"

    def test_api_error_with_status(self):
        from plugins.court_automation.preservation_quote.exceptions import APIError
        err = APIError("bad gateway", status_code=502)
        assert "502" in err.code

    def test_validation_error_with_errors(self):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        err = ValidationError("invalid input", errors={"field": "required"})
        assert err.errors == {"field": "required"}

    def test_company_list_empty_error(self):
        from plugins.court_automation.preservation_quote.exceptions import CompanyListEmptyError
        err = CompanyListEmptyError()
        assert "保险公司" in err.message

    def test_quote_execution_error(self):
        from plugins.court_automation.preservation_quote.exceptions import QuoteExecutionError
        err = QuoteExecutionError("failed", quote_id=42)
        assert err.quote_id == 42

    def test_retry_limit_exceeded_error(self):
        from plugins.court_automation.preservation_quote.exceptions import RetryLimitExceededError
        err = RetryLimitExceededError("too many retries", max_retries=3)
        assert err.max_retries == 3


class TestInsuranceHttpMixin:
    def test_build_premium_request(self):
        from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
        mixin = InsuranceHttpMixin()
        # Mock the premium_query_url property
        type(mixin).premium_query_url = property(lambda self: "https://example.com/api")
        headers, params, body, info = mixin._build_premium_request(
            bearer_token="test-token",
            preserve_amount=Decimal("100000"),
            institution="test-inst",
            corp_id="corp-1",
            timeout=30.0,
        )
        assert "Bearer" in headers
        assert headers["Bearer"] == "test-token"
        assert params["preserveAmount"] == "100000"

    def test_parse_premium_from_response_valid(self):
        from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
        mixin = InsuranceHttpMixin()
        result = mixin._parse_premium_from_response({"data": {"minPremium": "1234.56"}}, "inst", 1.0)
        assert result == Decimal("1234.56")

    def test_parse_premium_from_response_empty(self):
        from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
        mixin = InsuranceHttpMixin()
        result = mixin._parse_premium_from_response({}, "inst", 1.0)
        assert result is None

    def test_parse_premium_from_response_no_data(self):
        from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
        mixin = InsuranceHttpMixin()
        result = mixin._parse_premium_from_response({"data": None}, "inst", 1.0)
        assert result is None


class TestBaoquanTokenProvider:
    @pytest.mark.asyncio
    async def test_get_token_with_token_service(self):
        from plugins.court_automation.preservation_quote.preservation_quote.token_provider import BaoquanTokenProvider
        token_svc = MagicMock()
        token_svc.get_token.return_value = "valid-token"
        provider = BaoquanTokenProvider(token_service=token_svc)
        result = await provider.get_token()
        assert result == "valid-token"

    @pytest.mark.asyncio
    async def test_get_token_raises_when_no_token(self):
        from plugins.court_automation.preservation_quote.preservation_quote.token_provider import BaoquanTokenProvider
        from plugins.court_automation.preservation_quote.exceptions import TokenError
        token_svc = MagicMock()
        token_svc.get_token.return_value = None
        provider = BaoquanTokenProvider(token_service=token_svc)
        with pytest.raises(TokenError):
            await provider.get_token()
