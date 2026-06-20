"""Tests for insurance module services."""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================
# court_insurance_client.py
# ============================================================

class TestInsuranceCompany:
    """InsuranceCompany dataclass tests."""

    def test_create_insurance_company(self):
        from plugins.court_automation.preservation_quote.court_insurance_client import InsuranceCompany
        c = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        assert c.c_id == "1"
        assert c.c_code == "PICC"
        assert c.c_name == "人保"


class TestPremiumResult:
    """PremiumResult dataclass tests."""

    def test_success_result(self):
        from plugins.court_automation.preservation_quote.court_insurance_client import InsuranceCompany, PremiumResult
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = PremiumResult(
            company=company,
            premium=Decimal("100.50"),
            status="success",
            error_message=None,
            response_data={"data": {}},
        )
        assert result.premium == Decimal("100.50")
        assert result.status == "success"
        assert result.request_info is None

    def test_failed_result(self):
        from plugins.court_automation.preservation_quote.court_insurance_client import InsuranceCompany, PremiumResult
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = PremiumResult(
            company=company,
            premium=None,
            status="failed",
            error_message="timeout",
            response_data=None,
        )
        assert result.premium is None
        assert result.status == "failed"


class TestParseInsuranceCompanies:
    """Tests for _parse_insurance_companies."""

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx")
    def _make_client(self, mock_httpx, mock_config):
        mock_config.return_value = 60.0
        mock_httpx.AsyncClient.return_value = AsyncMock()
        mock_httpx.Limits.return_value = MagicMock()
        from plugins.court_automation.preservation_quote.court_insurance_client import CourtInsuranceClient
        return CourtInsuranceClient.__new__(CourtInsuranceClient)

    def test_parse_dict_with_data_key(self):
        client = self._make_client()
        data = {
            "data": [
                {"cId": "1", "cCode": "PICC", "cName": "人保"},
                {"cId": "2", "cCode": "CPIC", "cName": "太保"},
            ]
        }
        result = client._parse_insurance_companies(data)
        assert len(result) == 2
        assert result[0].c_code == "PICC"
        assert result[1].c_name == "太保"

    def test_parse_list_directly(self):
        client = self._make_client()
        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保"},
        ]
        result = client._parse_insurance_companies(data)
        assert len(result) == 1
        assert result[0].c_id == "1"

    def test_parse_unknown_format(self):
        client = self._make_client()
        result = client._parse_insurance_companies("invalid")
        assert result == []

    def test_parse_empty_data(self):
        client = self._make_client()
        result = client._parse_insurance_companies({"data": []})
        assert result == []

    def test_parse_skip_incomplete_items(self):
        client = self._make_client()
        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保"},
            {"cId": "2"},  # incomplete
            {"cCode": "CPIC"},  # incomplete
        ]
        result = client._parse_insurance_companies(data)
        assert len(result) == 1

    def test_parse_skip_non_dict_items(self):
        client = self._make_client()
        data = {"data": ["not_a_dict", {"cId": "1", "cCode": "PICC", "cName": "人保"}]}
        result = client._parse_insurance_companies(data)
        assert len(result) == 1


class TestFetchAllPremiumsEmpty:
    """Test fetch_all_premiums with empty companies."""

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx")
    def _make_client(self, mock_httpx, mock_config):
        mock_config.return_value = 60.0
        mock_httpx.AsyncClient.return_value = AsyncMock()
        mock_httpx.Limits.return_value = MagicMock()
        from plugins.court_automation.preservation_quote.court_insurance_client import CourtInsuranceClient
        return CourtInsuranceClient.__new__(CourtInsuranceClient)

    @pytest.mark.asyncio
    async def test_empty_companies_returns_empty(self):
        client = self._make_client()
        result = await client.fetch_all_premiums(
            bearer_token="tok",
            preserve_amount=Decimal("1000"),
            corp_id="2550",
            companies=[],
        )
        assert result == []


# ============================================================
# preservation_quote_service.py - _validate_create_params
# ============================================================

class TestValidateCreateParams:
    """Tests for PreservationQuoteService._validate_create_params."""

    def _make_service(self):
        from plugins.court_automation.preservation_quote.service import PreservationQuoteService
        svc = PreservationQuoteService.__new__(PreservationQuoteService)
        return svc

    def test_valid_params_pass(self):
        svc = self._make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("10000"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )

    def test_negative_amount_raises(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("-100"),
                corp_id="2550",
                category_id="127000",
                credential_id=None,
            )

    def test_zero_amount_raises(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("0"),
                corp_id="2550",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_corp_id_raises(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_category_id_raises(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="2550",
                category_id="  ",
                credential_id=None,
            )

    def test_negative_credential_id_raises(self):
        svc = self._make_service()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            svc._validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="2550",
                category_id="127000",
                credential_id=-1,
            )

    def test_none_credential_id_passes(self):
        svc = self._make_service()
        svc._validate_create_params(
            preserve_amount=Decimal("10000"),
            corp_id="2550",
            category_id="127000",
            credential_id=None,
        )


# ============================================================
# preservation_quote/repo.py - validate_create_params
# ============================================================

class TestRepoValidateCreateParams:
    """Tests for PreservationQuoteRepository.validate_create_params."""

    def _make_repo(self):
        from plugins.court_automation.preservation_quote.preservation_quote.repo import PreservationQuoteRepository
        return PreservationQuoteRepository()

    def test_valid_params(self):
        repo = self._make_repo()
        repo.validate_create_params(
            preserve_amount=Decimal("50000"),
            corp_id="2550",
            category_id="127000",
            credential_id=1,
        )

    def test_negative_amount_raises(self):
        repo = self._make_repo()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("-1"),
                corp_id="2550",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_corp_id_raises(self):
        repo = self._make_repo()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("100"),
                corp_id="",
                category_id="127000",
                credential_id=None,
            )

    def test_empty_category_id_raises(self):
        repo = self._make_repo()
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("100"),
                corp_id="2550",
                category_id="  ",
                credential_id=None,
            )


# ============================================================
# insurance exceptions
# ============================================================

class TestInsuranceExceptions:
    """Tests for insurance exception classes."""

    def test_token_error(self):
        from plugins.court_automation.preservation_quote.exceptions import TokenError
        e = TokenError("expired")
        assert e.message == "expired"
        assert e.code == "TOKEN_ERROR"

    def test_api_error(self):
        from plugins.court_automation.preservation_quote.exceptions import APIError
        e = APIError("bad response", status_code=500)
        assert "500" in e.code

    def test_network_error(self):
        from plugins.court_automation.preservation_quote.exceptions import NetworkError
        e = NetworkError("timeout")
        assert e.code == "NETWORK_ERROR"

    def test_validation_error_with_errors(self):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError
        e = ValidationError("bad data", errors={"field": "error"})
        assert e.errors == {"field": "error"}

    def test_company_list_empty_error(self):
        from plugins.court_automation.preservation_quote.exceptions import CompanyListEmptyError
        e = CompanyListEmptyError()
        assert e.code == "COMPANY_LIST_EMPTY"

    def test_quote_execution_error(self):
        from plugins.court_automation.preservation_quote.exceptions import QuoteExecutionError
        e = QuoteExecutionError("failed", quote_id=42)
        assert e.quote_id == 42

    def test_retry_limit_exceeded(self):
        from plugins.court_automation.preservation_quote.exceptions import RetryLimitExceededError
        e = RetryLimitExceededError("too many", max_retries=3)
        assert e.max_retries == 3
