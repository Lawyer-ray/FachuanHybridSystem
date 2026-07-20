"""保险模块测试 - 数据类、HTTP mixin、客户端解析。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.preservation_quote.insurance_http_mixin import InsuranceHttpMixin
from plugins.court_automation.preservation_quote.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)
from plugins.court_automation.preservation_quote.exceptions import (
    PreservationQuoteError,
    TokenError,
    APIError,
    NetworkError,
    ValidationError,
    CompanyListEmptyError,
    QuoteExecutionError,
    RetryLimitExceededError,
)


class TestInsuranceCompany:
    """测试 InsuranceCompany 数据类。"""

    def test_creation(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保财险")
        assert company.c_id == "1"
        assert company.c_code == "PICC"
        assert company.c_name == "人保财险"

    def test_str_fields(self) -> None:
        company = InsuranceCompany(c_id="123", c_code="ABC", c_name="测试公司")
        assert isinstance(company.c_id, str)
        assert isinstance(company.c_code, str)
        assert isinstance(company.c_name, str)


class TestPremiumResult:
    """测试 PremiumResult 数据类。"""

    def test_success_result(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保财险")
        result = PremiumResult(
            company=company,
            premium=Decimal("100.50"),
            status="success",
            error_message=None,
            response_data={"data": {"minPremium": 100.50}},
        )
        assert result.premium == Decimal("100.50")
        assert result.status == "success"
        assert result.error_message is None

    def test_failed_result(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保财险")
        result = PremiumResult(
            company=company,
            premium=None,
            status="failed",
            error_message="查询超时",
            response_data=None,
        )
        assert result.premium is None
        assert result.status == "failed"
        assert result.error_message == "查询超时"

    def test_with_request_info(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保财险")
        result = PremiumResult(
            company=company,
            premium=Decimal("200"),
            status="success",
            error_message=None,
            response_data={},
            request_info={"url": "https://example.com", "method": "POST"},
        )
        assert result.request_info is not None
        assert result.request_info["method"] == "POST"


class TestInsuranceHttpMixin:
    """测试 InsuranceHttpMixin。"""

    def setup_method(self) -> None:
        class ConcreteMixin(InsuranceHttpMixin):
            @property
            def premium_query_url(self) -> str:
                return "https://example.com/premium"

        self.mixin = ConcreteMixin()

    def test_build_premium_request(self) -> None:
        """测试请求构建。"""
        headers, params, body, request_info = self.mixin._build_premium_request(
            bearer_token="test-token-12345",
            preserve_amount=Decimal("10000"),
            institution="PICC",
            corp_id="CORP001",
            timeout=60.0,
        )
        assert headers["Bearer"] == "test-token-12345"
        assert params["institution"] == "PICC"
        assert params["corpId"] == "CORP001"
        assert params["preserveAmount"] == "10000"
        assert body["institution"] == "PICC"
        assert body["corpId"] == "CORP001"
        assert request_info["method"] == "POST"
        assert request_info["timeout"] == 60.0

    def test_build_premium_request_headers_contain_origin(self) -> None:
        headers, _, _, _ = self.mixin._build_premium_request("token", Decimal("100"), "INST", "CORP", 30.0)
        assert "Origin" in headers
        assert "zxfw.court.gov.cn" in headers["Origin"]

    def test_build_premium_request_preserve_amount_is_int_string(self) -> None:
        """保全金额转为整数字符串。"""
        _, params, body, _ = self.mixin._build_premium_request("token", Decimal("10000.50"), "INST", "CORP", 30.0)
        assert params["preserveAmount"] == "10000"
        assert body["preserveAmount"] == "10000"

    def test_parse_premium_from_response_with_min_premium(self) -> None:
        """解析 minPremium 字段。"""
        data = {"data": {"minPremium": 150.75}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result == Decimal("150.75")

    def test_parse_premium_from_response_with_min_amount(self) -> None:
        """解析 minAmount 字段（fallback）。"""
        data = {"data": {"minAmount": 200.00}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result == Decimal("200")

    def test_parse_premium_from_response_no_data(self) -> None:
        """无 data 字段返回 None。"""
        data = {}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result is None

    def test_parse_premium_from_response_empty_data(self) -> None:
        """空 data 返回 None。"""
        data = {"data": {}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result is None

    def test_parse_premium_from_response_no_premium_field(self) -> None:
        """data 中无 minPremium/minAmount 返回 None。"""
        data = {"data": {"other": "value"}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result is None

    def test_parse_premium_from_response_invalid_value(self) -> None:
        """无效金额值返回 None（不抛出异常）。"""
        data = {"data": {"minPremium": "not-a-number"}}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result is None

    def test_parse_premium_from_response_non_dict_data(self) -> None:
        """非 dict 的 data 返回 None（不抛出异常）。"""
        data = {"data": "invalid"}
        result = self.mixin._parse_premium_from_response(data, "PICC", 0.5)
        assert result is None

    def test_make_failed_result(self) -> None:
        """构建失败结果。"""
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保财险")
        request_info = {"url": "https://example.com", "method": "POST"}
        result = self.mixin._make_failed_result(
            company=company,
            error_label="查询超时",
            exc=TimeoutError("timeout"),
            request_info=request_info,
        )
        assert result.status == "failed"
        assert result.premium is None
        assert result.company.c_code == "PICC"
        assert "查询超时" in result.error_message
        assert "timeout" in result.error_message

    def test_make_failed_result_with_response_data(self) -> None:
        company = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = self.mixin._make_failed_result(
            company=company,
            error_label="HTTP 错误",
            exc=Exception("500"),
            request_info={"url": "https://example.com"},
            response_data={"error": "internal"},
        )
        assert result.response_data == {"error": "internal"}


class TestInsuranceExceptions:
    """测试保险异常类。"""

    def test_preservation_quote_error(self) -> None:
        exc = PreservationQuoteError("询价错误")
        assert "询价错误" in str(exc)
        assert exc.code == "PRESERVATION_QUOTE_ERROR"
        assert exc.status == 400

    def test_token_error(self) -> None:
        exc = TokenError("Token 过期")
        assert exc.code == "TOKEN_ERROR"
        assert exc.status == 401

    def test_api_error(self) -> None:
        exc = APIError("API 调用失败")
        assert exc.code == "API_ERROR"
        assert exc.status == 502

    def test_api_error_with_status_code(self) -> None:
        exc = APIError("API 调用失败", status_code=404)
        assert exc.code == "API_ERROR_404"

    def test_network_error(self) -> None:
        exc = NetworkError("网络超时")
        assert exc.code == "NETWORK_ERROR"
        assert exc.status == 504

    def test_validation_error(self) -> None:
        exc = ValidationError("数据无效", errors={"field": "required"})
        assert exc.code == "VALIDATION_ERROR"
        assert exc.errors == {"field": "required"}

    def test_validation_error_no_errors(self) -> None:
        exc = ValidationError("数据无效")
        assert exc.errors == {}

    def test_company_list_empty_error(self) -> None:
        exc = CompanyListEmptyError()
        assert exc.code == "COMPANY_LIST_EMPTY"
        assert exc.status == 404

    def test_quote_execution_error(self) -> None:
        exc = QuoteExecutionError("执行失败", quote_id=123)
        assert exc.code == "QUOTE_EXECUTION_ERROR"
        assert exc.quote_id == 123

    def test_retry_limit_exceeded_error(self) -> None:
        exc = RetryLimitExceededError("重试超限", max_retries=3)
        assert exc.code == "RETRY_LIMIT_EXCEEDED"
        assert exc.max_retries == 3
        assert exc.status == 429

    def test_exception_hierarchy(self) -> None:
        assert issubclass(TokenError, PreservationQuoteError)
        assert issubclass(APIError, PreservationQuoteError)
        assert issubclass(NetworkError, PreservationQuoteError)
        assert issubclass(ValidationError, PreservationQuoteError)
        assert issubclass(CompanyListEmptyError, PreservationQuoteError)
        assert issubclass(QuoteExecutionError, PreservationQuoteError)
        assert issubclass(RetryLimitExceededError, PreservationQuoteError)


class TestCourtInsuranceClientParseCompanies:
    """测试保险公司列表解析。"""

    def setup_method(self) -> None:
        with patch.object(CourtInsuranceClient, "__init__", lambda self, **kw: None):
            self.client = CourtInsuranceClient.__new__(CourtInsuranceClient)

    def test_parse_from_dict_with_data_key(self) -> None:
        data = {
            "data": [
                {"cId": "1", "cCode": "PICC", "cName": "人保财险"},
                {"cId": "2", "cCode": "CPIC", "cName": "太保财险"},
            ]
        }
        companies = self.client._parse_insurance_companies(data)
        assert len(companies) == 2
        assert companies[0].c_code == "PICC"
        assert companies[1].c_code == "CPIC"

    def test_parse_from_list(self) -> None:
        data = [
            {"cId": "1", "cCode": "PICC", "cName": "人保财险"},
        ]
        companies = self.client._parse_insurance_companies(data)
        assert len(companies) == 1

    def test_parse_empty_data(self) -> None:
        data = {"data": []}
        companies = self.client._parse_insurance_companies(data)
        assert companies == []

    def test_parse_unknown_format(self) -> None:
        companies = self.client._parse_insurance_companies("invalid")
        assert companies == []

    def test_parse_incomplete_item(self) -> None:
        """不完整的条目被跳过。"""
        data = {"data": [{"cId": "1", "cCode": "PICC"}]}
        companies = self.client._parse_insurance_companies(data)
        assert companies == []

    def test_parse_non_dict_item(self) -> None:
        """非 dict 条目被跳过。"""
        data = {"data": ["invalid", {"cId": "1", "cCode": "PICC", "cName": "人保"}]}
        companies = self.client._parse_insurance_companies(data)
        assert len(companies) == 1
