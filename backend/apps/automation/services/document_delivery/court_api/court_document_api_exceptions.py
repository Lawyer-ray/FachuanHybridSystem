"""API endpoints."""

from typing import Any

from apps.core.exceptions import ExternalServiceError, TokenError


class CourtApiError(ExternalServiceError):
    def __init__(
        self, message: str = "法院 API 调用错误", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "COURT_API_ERROR", errors=errors or {})


class TokenExpiredError(TokenError):
    def __init__(
        self, message: str = "Token 已过期", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "TOKEN_EXPIRED", errors=errors or {})


class ApiResponseError(CourtApiError):
    def __init__(
        self,
        message: str = "API 响应错误",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        response_code: int | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "API_RESPONSE_ERROR", errors=errors or {})
        self.response_code = response_code
