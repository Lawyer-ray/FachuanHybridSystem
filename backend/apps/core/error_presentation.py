"""Module for error presentation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    message: str
    errors: dict[str, Any]
    retryable: bool = False
    channel: str = "http"

    def to_payload(self, *, include_legacy_error: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "errors": self.errors or {},
            "retryable": bool(self.retryable),
        }
        if self.channel:
            payload["channel"] = self.channel
        if include_legacy_error:
            payload["error"] = self.message
        return payload


class ExceptionPresenter:
    def present(
        self,
        exc: Exception,
        *,
        channel: str,
        debug: bool = False,
    ) -> tuple[ErrorEnvelope, int | None]:
        from apps.core.exceptions_types import (
            AuthenticationError,
            BusinessException,
            ExternalServiceError,
            RecognitionTimeoutError,
            ServiceUnavailableError,
        )

        if isinstance(exc, BusinessException):
            status = self._status_for_business_exception(exc)
            retryable = self._retryable_for_business_exception(exc)
            return (
                ErrorEnvelope(
                    code=exc.code,
                    message=exc.message,
                    errors=exc.errors or {},
                    retryable=retryable,
                    channel=channel,
                ),
                status,
            )

        try:
            from apps.core.llm.exceptions import (
                LLMAPIError,
                LLMAuthenticationError,
                LLMBackendUnavailableError,
                LLMTimeoutError,
            )

            if isinstance(exc, LLMAuthenticationError):
                mapped_auth = AuthenticationError(
                    message=exc.message, code=exc.code, errors=getattr(exc, "errors", None)
                )
                return self.present(mapped_auth, channel=channel, debug=debug)

            if isinstance(exc, LLMBackendUnavailableError):
                mapped_unavail = ServiceUnavailableError(
                    message=exc.message, code=exc.code, errors=getattr(exc, "errors", None)
                )
                return self.present(mapped_unavail, channel=channel, debug=debug)

            if isinstance(exc, LLMTimeoutError):
                mapped_timeout = RecognitionTimeoutError(
                    message=exc.message, code=exc.code, errors=getattr(exc, "errors", None)
                )
                return self.present(mapped_timeout, channel=channel, debug=debug)

            if isinstance(exc, LLMAPIError):
                retryable = bool(
                    getattr(exc, "status_code", None) in (429, 500, 502, 503, 504)
                    or getattr(exc, "code", "") == "LLM_ALL_BACKENDS_UNAVAILABLE"
                )
                mapped_ext = ExternalServiceError(
                    message=exc.message, code=exc.code, errors=getattr(exc, "errors", None)
                )
                envelope, status = self.present(mapped_ext, channel=channel, debug=debug)
                return (
                    ErrorEnvelope(
                        code=envelope.code,
                        message=envelope.message,
                        errors=envelope.errors,
                        retryable=retryable,
                        channel=envelope.channel,
                    ),
                    status,
                )
        except Exception:
            logger.exception("操作失败")

            pass

        try:
            import openai

            if isinstance(exc, openai.AuthenticationError):
                mapped = AuthenticationError(
                    message="大模型鉴权失败,请检查配置", code="LLM_AUTH_ERROR", errors={"detail": str(exc)}
                )
                return self.present(mapped, channel=channel, debug=debug)
        except Exception:
            logger.exception("操作失败")

            pass

        message = str(exc) if debug else "系统错误,请稍后重试"
        return (
            ErrorEnvelope(code="INTERNAL_ERROR", message=message, errors={}, retryable=False, channel=channel),
            500 if channel == "http" else None,
        )

    def _status_for_business_exception(self, exc: Exception) -> int | None:
        from apps.core.exceptions_types import (
            AuthenticationError,
            ConflictError,
            ExternalServiceError,
            NotFoundError,
            PermissionDenied,
            RateLimitError,
            RecognitionTimeoutError,
            ServiceUnavailableError,
            ValidationException,
        )

        status = getattr(exc, "status", None)
        if isinstance(status, int) and 100 <= status <= 599:
            return status

        _STATUS_MAP: list[tuple[type, int]] = [
            (ValidationException, 400),
            (AuthenticationError, 401),
            (PermissionDenied, 403),
            (NotFoundError, 404),
            (ConflictError, 409),
            (RateLimitError, 429),
            (ServiceUnavailableError, 503),
            (RecognitionTimeoutError, 504),
            (ExternalServiceError, 502),
        ]
        for exc_type, code in _STATUS_MAP:
            if isinstance(exc, exc_type):
                return code
        return 400

    def _retryable_for_business_exception(self, exc: Exception) -> bool:
        from apps.core.exceptions_types import (
            ExternalServiceError,
            RateLimitError,
            RecognitionTimeoutError,
            ServiceUnavailableError,
        )

        return isinstance(exc, (RateLimitError, ServiceUnavailableError, RecognitionTimeoutError, ExternalServiceError))
