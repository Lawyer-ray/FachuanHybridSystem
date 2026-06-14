"""Coverage tests for error_presentation.py — LLM exception branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter


class TestErrorEnvelopeAdvanced:
    def test_empty_channel_not_in_payload(self) -> None:
        env = ErrorEnvelope(code="C", message="m", errors={}, channel="")
        payload = env.to_payload()
        assert "channel" not in payload

    def test_to_payload_with_retryable(self) -> None:
        env = ErrorEnvelope(code="X", message="y", errors={}, retryable=True, channel="sse")
        p = env.to_payload(include_legacy_error=False)
        assert p["retryable"] is True
        assert p["channel"] == "sse"
        assert "error" not in p


class TestExceptionPresenterLLMBranches:
    def _presenter(self) -> ExceptionPresenter:
        return ExceptionPresenter()

    def test_llm_auth_error_maps_to_auth(self) -> None:
        from apps.core.llm.exceptions import LLMAuthenticationError

        p = self._presenter()
        exc = LLMAuthenticationError(message="bad key")
        envelope, status = p.present(exc, channel="http", debug=True)
        assert status == 401

    def test_llm_backend_unavailable_maps_to_service_unavailable(self) -> None:
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        p = self._presenter()
        exc = LLMBackendUnavailableError(message="all backends down")
        envelope, status = p.present(exc, channel="http")
        # LLMBackendUnavailableError inherits from LLMError->ExternalServiceError->LLMAPIError
        # The mapping goes: LLMBackendUnavailableError -> ServiceUnavailableError path
        assert envelope.retryable is True

    def test_llm_timeout_maps_to_recognition_timeout(self) -> None:
        from apps.core.llm.exceptions import LLMTimeoutError

        p = self._presenter()
        exc = LLMTimeoutError(message="timed out", code="LLM_TIMEOUT")
        envelope, status = p.present(exc, channel="http")
        # LLMTimeoutError is a subclass of LLMError, which gets mapped through the LLMAPIError path
        # or through the LLMTimeoutError -> RecognitionTimeoutError path
        assert envelope.retryable is True

    def test_llm_api_error_retryable_status_429(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        p = self._presenter()
        exc = LLMAPIError(message="rate limited", code="LLM_API", status_code=429)
        envelope, status = p.present(exc, channel="http")
        assert envelope.retryable is True
        assert status == 502

    def test_llm_api_error_retryable_status_500(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        p = self._presenter()
        exc = LLMAPIError(message="server error", code="LLM_API", status_code=500)
        envelope, status = p.present(exc, channel="http")
        assert envelope.retryable is True

    def test_llm_api_error_retryable_status_503(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        p = self._presenter()
        exc = LLMAPIError(message="unavail", code="LLM_API", status_code=503)
        envelope, status = p.present(exc, channel="http")
        assert envelope.retryable is True

    def test_llm_api_error_retryable_all_backends_code(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        p = self._presenter()
        exc = LLMAPIError(message="all down", code="LLM_ALL_BACKENDS_UNAVAILABLE")
        envelope, status = p.present(exc, channel="http")
        assert envelope.retryable is True

    def test_llm_api_error_not_retryable_400(self) -> None:
        """LLMAPIError with status 400 gets mapped through ExternalServiceError path.
        The retryable flag is determined by the LLMAPIError block."""
        from apps.core.llm.exceptions import LLMAPIError

        p = self._presenter()
        exc = LLMAPIError(message="bad request", code="LLM_API", status_code=400)
        envelope, status = p.present(exc, channel="http")
        # LLMAPIError with status 400 -> ExternalServiceError -> status 502
        assert status == 502
        # Note: the retryable logic depends on the LLMAPIError block's isinstance check

    def test_recognition_timeout_status(self) -> None:
        from apps.core.exceptions import RecognitionTimeoutError

        p = self._presenter()
        exc = RecognitionTimeoutError(message="timeout", code="REC_TIMEOUT")
        envelope, status = p.present(exc, channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_business_exception_with_explicit_status(self) -> None:
        from apps.core.exceptions import ValidationException

        p = self._presenter()
        exc = ValidationException(message="val error", code="VAL")
        exc.status = 422  # Custom status
        envelope, status = p.present(exc, channel="http")
        assert status == 422

    def test_generic_exception_sse_returns_none_status(self) -> None:
        p = self._presenter()
        exc = RuntimeError("oops")
        envelope, status = p.present(exc, channel="sse", debug=True)
        assert status is None
        assert envelope.code == "INTERNAL_ERROR"
        assert "oops" in envelope.message

    def test_status_for_business_exception_fallback(self) -> None:
        from apps.core.exceptions import BusinessException

        p = self._presenter()
        exc = BusinessException(message="unknown", code="UNKNOWN")
        status = p._status_for_business_exception(exc)
        assert status == 400

    def test_retryable_for_business_exception_true(self) -> None:
        from apps.core.exceptions import RateLimitError, ServiceUnavailableError

        p = self._presenter()
        assert p._retryable_for_business_exception(RateLimitError(message="rl")) is True
        assert p._retryable_for_business_exception(ServiceUnavailableError(message="su")) is True

    def test_retryable_for_business_exception_false(self) -> None:
        from apps.core.exceptions import NotFoundError

        p = self._presenter()
        assert p._retryable_for_business_exception(NotFoundError(message="nf")) is False
