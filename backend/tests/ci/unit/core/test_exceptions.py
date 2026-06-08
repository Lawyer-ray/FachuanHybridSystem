"""测试 core.exceptions 子模块

覆盖: base.py, common.py, external.py, llm/exceptions.py, error_codes.py, error_catalog.py
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import (
    AuthenticationError,
    BusinessException,
    BusinessError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    UnauthorizedError,
    ValidationException,
)


# ============================================================
# BusinessException / BusinessError
# ============================================================


class TestBusinessException:
    """测试 BusinessException 基类"""

    def test_init_defaults(self) -> None:
        exc = BusinessException("something failed")
        assert exc.message == "something failed"
        assert exc.code == "BusinessException"
        assert exc.errors == {}

    def test_init_custom_code(self) -> None:
        exc = BusinessException("msg", code="MY_ERROR", errors={"field": "bad"})
        assert exc.code == "MY_ERROR"
        assert exc.errors == {"field": "bad"}

    def test_str(self) -> None:
        exc = BusinessException("msg", code="C")
        assert str(exc) == "C: msg"

    def test_repr(self) -> None:
        exc = BusinessException("msg", code="C")
        assert "BusinessException" in repr(exc)
        assert "msg" in repr(exc)

    def test_to_dict(self) -> None:
        exc = BusinessException("error msg", code="ERR", errors={"f": "v"})
        d = exc.to_dict()
        assert d["success"] is False
        assert d["code"] == "ERR"
        assert d["message"] == "error msg"
        assert d["errors"] == {"f": "v"}


class TestBusinessError:
    def test_init(self) -> None:
        exc = BusinessError("bad request")
        assert exc.status == 400
        assert exc.code == "BUSINESS_ERROR"


# ============================================================
# Common exceptions
# ============================================================


class TestCommonExceptions:
    """测试通用异常"""

    def test_validation_exception(self) -> None:
        exc = ValidationException("invalid input")
        assert isinstance(exc, BusinessException)
        assert exc.code == "VALIDATION_ERROR"

    def test_permission_denied(self) -> None:
        exc = PermissionDenied("forbidden")
        assert isinstance(exc, BusinessException)
        assert exc.code == "PERMISSION_DENIED"

    def test_not_found_error(self) -> None:
        exc = NotFoundError("resource not found")
        assert isinstance(exc, BusinessException)
        assert exc.code == "NOT_FOUND"

    def test_conflict_error(self) -> None:
        exc = ConflictError("already exists")
        assert isinstance(exc, BusinessException)
        assert exc.code == "CONFLICT"

    def test_authentication_error(self) -> None:
        exc = AuthenticationError("need login")
        assert isinstance(exc, BusinessException)
        assert exc.code == "AUTHENTICATION_ERROR"

    def test_forbidden_error(self) -> None:
        exc = ForbiddenError("no access")
        assert isinstance(exc, BusinessException)
        assert exc.code == "PERMISSION_DENIED"

    def test_rate_limit_error(self) -> None:
        exc = RateLimitError("too fast", errors={"retry_after": 60})
        assert isinstance(exc, BusinessException)
        assert "RATE_LIMIT" in exc.code
        assert exc.errors.get("retry_after") == 60

    def test_unauthorized_error(self) -> None:
        exc = UnauthorizedError("unauthorized")
        assert isinstance(exc, BusinessException)


# ============================================================
# External service exceptions
# ============================================================


class TestExternalExceptions:
    """测试外部服务异常"""

    def test_external_service_error(self) -> None:
        from apps.core.exceptions import ExternalServiceError

        exc = ExternalServiceError("service down", code="SVC_DOWN", errors={"status": 503})
        assert isinstance(exc, BusinessException)
        assert exc.code == "SVC_DOWN"

    def test_service_unavailable(self) -> None:
        from apps.core.exceptions import ServiceUnavailableError

        exc = ServiceUnavailableError("unavailable")
        assert exc.code == "SERVICE_UNAVAILABLE"

    def test_network_error(self) -> None:
        from apps.core.exceptions import NetworkError

        exc = NetworkError("connection failed")
        assert exc.code == "NETWORK_ERROR"

    def test_api_error(self) -> None:
        from apps.core.exceptions import APIError

        exc = APIError("api error")
        assert exc.code == "API_ERROR"

    def test_token_error(self) -> None:
        from apps.core.exceptions import TokenError

        exc = TokenError("token expired")
        assert exc.code == "TOKEN_ERROR"

    def test_browser_automation_error(self) -> None:
        from apps.core.exceptions import BrowserAutomationError

        exc = BrowserAutomationError("browser crashed")
        assert exc.code == "BROWSER_AUTOMATION_ERROR"


# ============================================================
# LLM exceptions
# ============================================================


class TestLLMExceptions:
    """测试 LLM 异常层次"""

    def test_llm_error_base(self) -> None:
        from apps.core.llm.exceptions import LLMError

        exc = LLMError("llm failed")
        assert exc.code == "LLM_ERROR"
        assert isinstance(exc, BusinessException)

    def test_llm_network_error(self) -> None:
        from apps.core.llm.exceptions import LLMError, LLMNetworkError

        exc = LLMNetworkError("network down")
        assert exc.code == "LLM_NETWORK_ERROR"
        assert isinstance(exc, LLMError)

    def test_llm_api_error(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("bad response", status_code=429)
        assert exc.code == "LLM_API_ERROR"
        assert exc.status_code == 429
        assert exc.errors.get("status_code") == 429

    def test_llm_api_error_no_status(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("error")
        assert exc.status_code is None

    def test_llm_authentication_error(self) -> None:
        from apps.core.llm.exceptions import LLMAuthenticationError

        exc = LLMAuthenticationError()
        assert exc.code == "LLM_AUTH_ERROR"

    def test_llm_backend_unavailable(self) -> None:
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        exc = LLMBackendUnavailableError()
        assert exc.code == "LLM_ALL_BACKENDS_UNAVAILABLE"

    def test_llm_timeout_error(self) -> None:
        from apps.core.llm.exceptions import LLMTimeoutError

        exc = LLMTimeoutError(timeout_seconds=30.0)
        assert exc.code == "LLM_TIMEOUT"
        assert exc.timeout_seconds == 30.0

    def test_llm_timeout_error_no_timeout(self) -> None:
        from apps.core.llm.exceptions import LLMTimeoutError

        exc = LLMTimeoutError()
        assert exc.timeout_seconds is None
