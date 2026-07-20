"""
Refactored pure data processing tests for CourtInsuranceClient and InsuranceHttpMixin.

Tests the extracted data parsing / validation logic that does NOT require
network access, database, or external services.
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.preservation_quote.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
    parse_insurance_companies,
)
from plugins.court_automation.preservation_quote.insurance_http_mixin import (
    InsuranceHttpMixin,
    parse_premium_from_response,
    build_premium_request,
    make_failed_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_insurance_client() -> CourtInsuranceClient:
    """Create a CourtInsuranceClient bypassing __init__ (no httpx setup)."""
    client = CourtInsuranceClient.__new__(CourtInsuranceClient)
    client._token_service = MagicMock()
    client._client = MagicMock()
    return client


class _StubHttpMixin(InsuranceHttpMixin):
    """Concrete subclass with a configurable premium_query_url."""

    def __init__(self, url: str = "https://example.com/premium") -> None:
        self._url = url

    @property
    def premium_query_url(self) -> str:
        return self._url


def _make_http_mixin(url: str = "https://example.com/premium") -> _StubHttpMixin:
    return _StubHttpMixin(url)


# ═══════════════════════════════════════════════════════════════════════════
# parse_insurance_companies (via class method, delegates to pure function)
# ═══════════════════════════════════════════════════════════════════════════

class TestParseInsuranceCompanies:
    """Test _parse_insurance_companies pure data extraction."""

    def test_standard_response_with_data_key(self) -> None:
        client = _make_insurance_client()
        data = {
            "data": [
                {"cId": "1", "cCode": "PICC", "cName": "人保"},
                {"cId": "2", "cCode": "CPIC", "cName": "太保"},
            ]
        }
        result = client._parse_insurance_companies(data)
        assert len(result) == 2
        assert result[0].c_id == "1"
        assert result[0].c_code == "PICC"
        assert result[1].c_name == "太保"

    def test_flat_list_response(self) -> None:
        client = _make_insurance_client()
        data = [{"cId": "10", "cCode": "PINGAN", "cName": "平安"}]
        result = client._parse_insurance_companies(data)
        assert len(result) == 1
        assert result[0].c_code == "PINGAN"

    def test_empty_data_key(self) -> None:
        client = _make_insurance_client()
        assert client._parse_insurance_companies({"data": []}) == []

    def test_empty_list(self) -> None:
        client = _make_insurance_client()
        assert client._parse_insurance_companies([]) == []

    def test_unknown_format_returns_empty(self) -> None:
        client = _make_insurance_client()
        assert client._parse_insurance_companies("unexpected") == []

    def test_missing_fields_skip_item(self) -> None:
        client = _make_insurance_client()
        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保"},
            {"cId": "2", "cCode": "", "cName": "太保"},
            {"cCode": "CPIC", "cName": "太保"},
            {"cId": "4", "cCode": "CCIC", "cName": ""},
        ]
        result = client._parse_insurance_companies(data)
        assert len(result) == 1
        assert result[0].c_id == "1"

    def test_non_dict_items_skipped(self) -> None:
        client = _make_insurance_client()
        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保"},
            "not a dict",
            42,
            None,
        ]
        assert len(client._parse_insurance_companies(data)) == 1

    def test_numeric_ids_are_cast_to_str(self) -> None:
        client = _make_insurance_client()
        data = [{"cId": 100, "cCode": 200, "cName": "人保"}]
        result = client._parse_insurance_companies(data)
        assert result[0].c_id == "100"
        assert result[0].c_code == "200"

    def test_none_input_returns_empty(self) -> None:
        client = _make_insurance_client()
        assert client._parse_insurance_companies(None) == []

    def test_many_companies(self) -> None:
        client = _make_insurance_client()
        data = [{"cId": str(i), "cCode": f"C{i}", "cName": f"公司{i}"} for i in range(50)]
        result = client._parse_insurance_companies(data)
        assert len(result) == 50
        assert result[49].c_name == "公司49"


# ═══════════════════════════════════════════════════════════════════════════
# _parse_premium_from_response (via class method)
# ═══════════════════════════════════════════════════════════════════════════

class TestParsePremiumFromResponse:
    """Test _parse_premium_from_response pure data extraction."""

    def test_min_premium_present(self) -> None:
        mixin = _make_http_mixin()
        data = {"data": {"minPremium": "1500.50", "minAmount": "2000.00"}}
        assert mixin._parse_premium_from_response(data, "PICC", 1.0) == Decimal("1500.50")

    def test_falls_back_to_min_amount(self) -> None:
        mixin = _make_http_mixin()
        data = {"data": {"minPremium": None, "minAmount": "3000"}}
        assert mixin._parse_premium_from_response(data, "PICC", 1.0) == Decimal("3000")

    def test_both_none_returns_none(self) -> None:
        mixin = _make_http_mixin()
        data = {"data": {"minPremium": None, "minAmount": None}}
        assert mixin._parse_premium_from_response(data, "PICC", 1.0) is None

    def test_empty_data_returns_none(self) -> None:
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": {}}, "PICC", 1.0) is None

    def test_no_data_key_returns_none(self) -> None:
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({}, "PICC", 1.0) is None

    def test_non_dict_data_returns_none(self) -> None:
        """Returns None when data value is not a dict."""
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": "invalid"}, "PICC", 1.0) is None

    def test_non_numeric_premium_returns_none(self) -> None:
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": {"minPremium": "abc"}}, "PICC", 1.0) is None

    def test_integer_premium(self) -> None:
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": {"minPremium": 5000}}, "PICC", 1.0) == Decimal("5000")

    def test_empty_string_premium_returns_none(self) -> None:
        """Empty string is falsy, falls through to minAmount which is also empty."""
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": {"minPremium": "", "minAmount": ""}}, "PICC", 1.0) is None

    def test_zero_premium(self) -> None:
        mixin = _make_http_mixin()
        assert mixin._parse_premium_from_response({"data": {"minPremium": "0"}}, "PICC", 1.0) == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# _build_premium_request (via class method with concrete subclass)
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPremiumRequest:
    """Test _build_premium_request pure request construction."""

    def test_returns_four_elements(self) -> None:
        mixin = _make_http_mixin("https://example.com/premium")
        result = mixin._build_premium_request("token123", Decimal("10000"), "PICC", "corp1", 60.0)
        assert len(result) == 4
        headers, params, body, request_info = result
        assert isinstance(headers, dict)
        assert isinstance(params, dict)
        assert isinstance(body, dict)
        assert isinstance(request_info, dict)

    def test_headers_contain_bearer_token(self) -> None:
        mixin = _make_http_mixin("https://example.com")
        headers, _, _, _ = mixin._build_premium_request("mytoken", Decimal("10000"), "PICC", "corp1", 60.0)
        assert headers["Bearer"] == "mytoken"

    def test_params_contain_institution(self) -> None:
        mixin = _make_http_mixin("https://example.com")
        _, params, _, _ = mixin._build_premium_request("t", Decimal("10000"), "PICC_CODE", "corp1", 60.0)
        assert params["institution"] == "PICC_CODE"

    def test_body_has_preserve_amount_as_int_string(self) -> None:
        mixin = _make_http_mixin("https://example.com")
        _, _, body, _ = mixin._build_premium_request("t", Decimal("10050.75"), "PICC", "corp1", 60.0)
        assert body["preserveAmount"] == "10050"

    def test_request_info_structure(self) -> None:
        url = "https://example.com/premium"
        mixin = _make_http_mixin(url)
        _, _, _, info = mixin._build_premium_request("t", Decimal("10000"), "PICC", "corp1", 60.0)
        assert info["url"] == url
        assert info["method"] == "POST"
        assert info["timeout"] == 60.0
        assert "timestamp" in info
        assert "params" in info
        assert "body" in info

    def test_bearer_token_truncated_in_request_info_headers(self) -> None:
        mixin = _make_http_mixin("https://example.com")
        long_token = "x" * 100
        _, _, _, info = mixin._build_premium_request(long_token, Decimal("10000"), "PICC", "corp1", 60.0)
        assert len(info["headers"]["Bearer"]) < 100
        assert "..." in info["headers"]["Bearer"]

    def test_params_has_time_key(self) -> None:
        mixin = _make_http_mixin("https://example.com")
        _, params, _, _ = mixin._build_premium_request("t", Decimal("10000"), "PICC", "corp1", 60.0)
        assert "time" in params
        assert params["time"].isdigit()


# ═══════════════════════════════════════════════════════════════════════════
# _make_failed_result (via class method)
# ═══════════════════════════════════════════════════════════════════════════

class TestMakeFailedResult:
    """Test _make_failed_result constructs PremiumResult correctly."""

    def test_failed_result_status(self) -> None:
        mixin = _make_http_mixin()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = mixin._make_failed_result(company, "timeout", TimeoutError("boom"), {"url": "https://example.com"})
        assert result.status == "failed"
        assert result.premium is None

    def test_failed_result_contains_error_info(self) -> None:
        mixin = _make_http_mixin()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = mixin._make_failed_result(company, "HTTP 500", RuntimeError("server error"), {"url": "https://example.com"})
        assert "HTTP 500" in result.error_message
        assert "RuntimeError" in result.error_message

    def test_failed_result_preserves_company(self) -> None:
        mixin = _make_http_mixin()
        company = InsuranceCompany(c_id="99", c_code="TEST", c_name="测试保险")
        result = mixin._make_failed_result(company, "err", Exception("e"), {"url": "https://example.com"})
        assert result.company.c_code == "TEST"
        assert result.company.c_name == "测试保险"

    def test_failed_result_with_response_data(self) -> None:
        mixin = _make_http_mixin()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        resp = {"error": "forbidden"}
        result = mixin._make_failed_result(
            company, "HTTP 403", Exception("forbidden"), {"url": "https://example.com"}, response_data=resp
        )
        assert result.response_data == resp

    def test_failed_result_request_info(self) -> None:
        mixin = _make_http_mixin()
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        info = {"url": "https://test.com", "method": "POST"}
        result = mixin._make_failed_result(company, "err", Exception("e"), info)
        assert result.request_info == info


# ═══════════════════════════════════════════════════════════════════════════
# Module-level pure function: parse_insurance_companies
# ═══════════════════════════════════════════════════════════════════════════

class TestParseInsuranceCompaniesPureFunction:
    """Test parse_insurance_companies as a module-level pure function."""

    def test_standard_dict_response(self) -> None:
        data = {"data": [{"cId": "1", "cCode": "PICC", "cName": "人保"}]}
        result = parse_insurance_companies(data)
        assert len(result) == 1
        assert result[0].c_code == "PICC"

    def test_list_response(self) -> None:
        data = [{"cId": "1", "cCode": "PICC", "cName": "人保"}]
        result = parse_insurance_companies(data)
        assert len(result) == 1

    def test_empty_data(self) -> None:
        assert parse_insurance_companies({"data": []}) == []

    def test_none_returns_empty(self) -> None:
        assert parse_insurance_companies(None) == []

    def test_missing_fields_skipped(self) -> None:
        data = [{"cId": "1", "cCode": "", "cName": "人保"}]
        result = parse_insurance_companies(data)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Module-level pure function: parse_premium_from_response
# ═══════════════════════════════════════════════════════════════════════════

class TestParsePremiumPureFunction:
    """Test parse_premium_from_response as a module-level pure function."""

    def test_min_premium_present(self) -> None:
        data = {"data": {"minPremium": "1500.50"}}
        assert parse_premium_from_response(data, "PICC") == Decimal("1500.50")

    def test_falls_back_to_min_amount(self) -> None:
        data = {"data": {"minPremium": None, "minAmount": "3000"}}
        assert parse_premium_from_response(data, "PICC") == Decimal("3000")

    def test_empty_data_returns_none(self) -> None:
        assert parse_premium_from_response({}, "PICC") is None

    def test_non_numeric_returns_none(self) -> None:
        data = {"data": {"minPremium": "abc"}}
        assert parse_premium_from_response(data, "PICC") is None


# ═══════════════════════════════════════════════════════════════════════════
# Module-level pure function: build_premium_request
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPremiumRequestPureFunction:
    """Test build_premium_request as a module-level pure function."""

    def test_returns_four_elements(self) -> None:
        result = build_premium_request("https://api.test", "tok", Decimal("10000"), "PICC", "corp1", 60.0)
        assert len(result) == 4

    def test_headers_contain_bearer(self) -> None:
        headers, _, _, _ = build_premium_request("https://api.test", "mytoken", Decimal("10000"), "PICC", "corp1", 60.0)
        assert headers["Bearer"] == "mytoken"

    def test_body_has_amount(self) -> None:
        _, _, body, _ = build_premium_request("https://api.test", "tok", Decimal("10050.75"), "PICC", "corp1", 60.0)
        assert body["preserveAmount"] == "10050"

    def test_request_info_url(self) -> None:
        _, _, _, info = build_premium_request("https://api.test/premium", "tok", Decimal("10000"), "PICC", "corp1", 60.0)
        assert info["url"] == "https://api.test/premium"


# ═══════════════════════════════════════════════════════════════════════════
# Module-level pure function: make_failed_result
# ═══════════════════════════════════════════════════════════════════════════

class TestMakeFailedResultPureFunction:
    """Test make_failed_result as a module-level pure function."""

    def test_returns_failed_status(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = make_failed_result(company, "timeout", TimeoutError("boom"), {"url": "x"})
        assert result.status == "failed"
        assert result.premium is None

    def test_error_message_contains_label(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = make_failed_result(company, "HTTP 500", RuntimeError("err"), {"url": "x"})
        assert "HTTP 500" in result.error_message

    def test_preserves_company(self) -> None:
        company = InsuranceCompany(c_id="99", c_code="TEST", c_name="测试")
        result = make_failed_result(company, "err", Exception("e"), {"url": "x"})
        assert result.company.c_code == "TEST"
