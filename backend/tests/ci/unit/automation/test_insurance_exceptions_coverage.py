"""测试财产保全询价异常类

覆盖: apps/automation/services/insurance/exceptions.py
"""

from __future__ import annotations

import pytest

from apps.automation.services.insurance.exceptions import (
    APIError,
    CompanyListEmptyError,
    NetworkError,
    PreservationQuoteError,
    QuoteExecutionError,
    RetryLimitExceededError,
    TokenError,
    ValidationError,
)


class TestPreservationQuoteError:
    """测试基类"""

    def test_default_code(self) -> None:
        err = PreservationQuoteError("msg")
        assert err.code == "PRESERVATION_QUOTE_ERROR"
        assert err.status == 400

    def test_custom_code(self) -> None:
        err = PreservationQuoteError("msg", code="CUSTOM", status=500)
        assert err.code == "CUSTOM"
        assert err.status == 500


class TestTokenError:
    def test_code_and_status(self) -> None:
        err = TokenError("token expired")
        assert err.code == "TOKEN_ERROR"
        assert err.status == 401
        assert "token expired" in str(err)


class TestAPIError:
    def test_default_code(self) -> None:
        err = APIError("api failed")
        assert err.code == "API_ERROR"
        assert err.status == 502

    def test_with_status_code(self) -> None:
        err = APIError("api failed", status_code=404)
        assert err.code == "API_ERROR_404"

    def test_none_status_code(self) -> None:
        err = APIError("api failed", status_code=None)
        assert err.code == "API_ERROR"


class TestNetworkError:
    def test_code_and_status(self) -> None:
        err = NetworkError("timeout")
        assert err.code == "NETWORK_ERROR"
        assert err.status == 504


class TestValidationError:
    def test_code_and_status(self) -> None:
        err = ValidationError("invalid input")
        assert err.code == "VALIDATION_ERROR"
        assert err.status == 400
        assert err.errors == {}

    def test_with_errors(self) -> None:
        err = ValidationError("invalid", errors={"field": "required"})
        assert err.errors == {"field": "required"}


class TestCompanyListEmptyError:
    def test_default_message(self) -> None:
        err = CompanyListEmptyError()
        assert "未获取到保险公司列表" in str(err)
        assert err.code == "COMPANY_LIST_EMPTY"
        assert err.status == 404

    def test_custom_message(self) -> None:
        err = CompanyListEmptyError(message="custom msg")
        assert "custom msg" in str(err)


class TestQuoteExecutionError:
    def test_code_and_status(self) -> None:
        err = QuoteExecutionError("failed")
        assert err.code == "QUOTE_EXECUTION_ERROR"
        assert err.status == 500
        assert err.quote_id is None

    def test_with_quote_id(self) -> None:
        err = QuoteExecutionError("failed", quote_id=42)
        assert err.quote_id == 42


class TestRetryLimitExceededError:
    def test_code_and_status(self) -> None:
        err = RetryLimitExceededError("too many retries")
        assert err.code == "RETRY_LIMIT_EXCEEDED"
        assert err.status == 429
        assert err.max_retries is None

    def test_with_max_retries(self) -> None:
        err = RetryLimitExceededError("too many", max_retries=5)
        assert err.max_retries == 5


class TestInheritance:
    """测试异常继承关系"""

    def test_all_inherit_from_preservation_quote_error(self) -> None:
        for cls in (
            TokenError, APIError, NetworkError, ValidationError,
            CompanyListEmptyError, QuoteExecutionError, RetryLimitExceededError,
        ):
            assert issubclass(cls, PreservationQuoteError)

    def test_all_inherit_from_business_error(self) -> None:
        from apps.core.exceptions import BusinessError
        for cls in (
            TokenError, APIError, NetworkError, ValidationError,
            CompanyListEmptyError, QuoteExecutionError, RetryLimitExceededError,
        ):
            assert issubclass(cls, BusinessError)
