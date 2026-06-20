"""Tests for CourtInsuranceClient and InsuranceHttpMixin."""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
from plugins.court_automation.preservation_quote.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)


class TestInsuranceCompany:
    def test_dataclass(self):
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        assert company.c_id == "1"
        assert company.c_code == "PICC"
        assert company.c_name == "人保"


class TestPremiumResult:
    def test_dataclass(self):
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

    def test_request_info_optional(self):
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = PremiumResult(
            company=company,
            premium=None,
            status="failed",
            error_message="error",
            response_data=None,
        )
        assert result.request_info is None


class TestInsuranceHttpMixin:
    def setup_method(self):
        self.mixin = InsuranceHttpMixin()

    def test_premium_query_url_not_implemented(self):
        with pytest.raises(NotImplementedError):
            _ = self.mixin.premium_query_url

    def test_parse_premium_from_response_with_minPremium(self):
        data = {"data": {"minPremium": 150.75}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 1.0)
        assert result == Decimal("150.75")

    def test_parse_premium_from_response_with_minAmount(self):
        data = {"data": {"minAmount": 200}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 1.0)
        assert result == Decimal("200")

    def test_parse_premium_from_response_no_data(self):
        result = self.mixin._parse_premium_from_response({}, "PICC", 1.0)
        assert result is None

    def test_parse_premium_from_response_none_data(self):
        result = self.mixin._parse_premium_from_response({"data": None}, "PICC", 1.0)
        assert result is None

    def test_parse_premium_from_response_non_dict_data(self):
        result = self.mixin._parse_premium_from_response("not a dict", "PICC", 1.0)
        assert result is None

    def test_parse_premium_from_response_none_premium(self):
        data = {"data": {"minPremium": None, "minAmount": None}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 1.0)
        assert result is None

    def test_parse_premium_no_premium_fields(self):
        data = {"data": {"other_field": 100}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 1.0)
        assert result is None

    def test_build_premium_request(self):
        self.mixin._premium_query_url = "https://example.com/api"
        # Override property for test
        InsuranceHttpMixin.premium_query_url = property(lambda self: "https://example.com/api")

        headers, params, body, info = self.mixin._build_premium_request(
            bearer_token="test_token",
            preserve_amount=Decimal("10000"),
            institution="PICC",
            corp_id="12345",
            timeout=30.0,
        )

        assert "Bearer" in headers
        assert headers["Bearer"] == "test_token"
        assert params["institution"] == "PICC"
        assert params["preserveAmount"] == "10000"
        assert body["institution"] == "PICC"
        assert info["method"] == "POST"
        assert info["timeout"] == 30.0

    def test_make_failed_result(self):
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        request_info = {"url": "https://test.com", "method": "POST"}

        result = self.mixin._make_failed_result(
            company=company,
            error_label="测试错误",
            exc=ValueError("test error"),
            request_info=request_info,
        )

        assert result.company == company
        assert result.premium is None
        assert result.status == "failed"
        assert "测试错误" in result.error_message
        assert result.request_info == request_info

    def test_make_failed_result_with_response_data(self):
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        request_info = {"url": "https://test.com"}
        response_data = {"error": "bad request"}

        result = self.mixin._make_failed_result(
            company=company,
            error_label="HTTP 错误",
            exc=Exception("400"),
            request_info=request_info,
            response_data=response_data,
            log_level="error",
        )

        assert result.response_data == response_data


class TestCourtInsuranceClient:
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_init(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())
        assert client._token_service is not None

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_token_service_lazy_load(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=None)
        with patch("apps.core.interfaces.ServiceLocator.get_token_service") as mock_get:
            mock_get.return_value = MagicMock()
            ts = client.token_service
            assert ts is not None

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_properties(self, mock_client_cls, mock_get_config):
        def config_side_effect(key, default=None):
            configs = {
                "services.insurance.max_keepalive_connections": 20,
                "services.insurance.keepalive_expiry": 30.0,
                "services.insurance.max_connections": 100,
                "services.insurance.default_timeout": 60.0,
                "services.insurance.list_url": "https://example.com/list",
                "services.insurance.premium_query_url": "https://example.com/premium",
            }
            return configs.get(key, default)

        mock_get_config.side_effect = config_side_effect
        client = CourtInsuranceClient(token_service=MagicMock())
        assert client.default_timeout == 60.0
        assert client.max_connections == 100
        assert "example.com" in client.insurance_list_url
        assert "example.com" in client.premium_query_url

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_parse_insurance_companies_from_dict(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())

        data = {
            "data": [
                {"cId": "1", "cCode": "PICC", "cName": "人保"},
                {"cId": "2", "cCode": "CPIC", "cName": "太保"},
            ]
        }
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 2
        assert companies[0].c_code == "PICC"
        assert companies[1].c_code == "CPIC"

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_parse_insurance_companies_from_list(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())

        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保"},
        ]
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_parse_insurance_companies_unknown_format(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())

        companies = client._parse_insurance_companies("unexpected")
        assert companies == []

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_parse_insurance_companies_incomplete(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())

        data = {"data": [{"cId": "1", "cCode": "PICC"}, {"cId": "2", "cCode": "X", "cName": "完整"}]}
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1
        assert companies[0].c_name == "完整"

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_parse_insurance_companies_non_dict_item(self, mock_client_cls, mock_get_config):
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())

        data = {"data": ["not_a_dict", {"cId": "1", "cCode": "X", "cName": "Y"}]}
        companies = client._parse_insurance_companies(data)
        assert len(companies) == 1


class TestCourtInsuranceClientAsync:
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_fetch_all_premiums_empty_companies(self, mock_client_cls, mock_get_config):
        import asyncio
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())
        result = asyncio.run(client.fetch_all_premiums(
            bearer_token="token",
            preserve_amount=Decimal("10000"),
            corp_id="123",
            companies=[],
        ))
        assert result == []

    @patch("plugins.court_automation.preservation_quote.court_insurance_client.get_config")
    @patch("plugins.court_automation.preservation_quote.court_insurance_client.httpx.AsyncClient")
    def test_context_manager(self, mock_client_cls, mock_get_config):
        import asyncio
        mock_get_config.return_value = 60.0
        client = CourtInsuranceClient(token_service=MagicMock())
        # Test async context manager protocol
        assert hasattr(client, '__aenter__')
        assert hasattr(client, '__aexit__')
