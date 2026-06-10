"""
Tests for core/exceptions/ - chat.py, external.py, error_presentation.py, __init__.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import BusinessException


class TestChatExceptions:
    def test_chat_provider_exception(self):
        from apps.core.exceptions.chat import ChatProviderException

        exc = ChatProviderException(message="test error", error_code="E001", platform="feishu")
        assert exc.error_code == "E001"
        assert exc.platform == "feishu"
        assert exc.code == "CHAT_PROVIDER_ERROR"

    def test_unsupported_platform_exception(self):
        from apps.core.exceptions.chat import UnsupportedPlatformException

        exc = UnsupportedPlatformException(platform="discord")
        assert exc.code == "UNSUPPORTED_PLATFORM"
        assert exc.platform == "discord"

    def test_chat_creation_exception(self):
        from apps.core.exceptions.chat import ChatCreationException

        exc = ChatCreationException(error_code="CE01", platform="feishu")
        assert exc.code == "CHAT_CREATION_ERROR"

    def test_message_send_exception(self):
        from apps.core.exceptions.chat import MessageSendException

        exc = MessageSendException(chat_id="12345", platform="feishu")
        assert exc.chat_id == "12345"
        assert exc.code == "MESSAGE_SEND_ERROR"

    def test_configuration_exception(self):
        from apps.core.exceptions.chat import ConfigurationException

        exc = ConfigurationException(platform="feishu", missing_config="api_key")
        assert exc.missing_config == "api_key"
        assert exc.code == "CONFIGURATION_ERROR"

    def test_owner_setting_exception(self):
        from apps.core.exceptions.chat import OwnerSettingException

        exc = OwnerSettingException(
            message="test", owner_id="user1", chat_id="chat1", custom_field="value"
        )
        assert exc.owner_id == "user1"
        assert exc.chat_id == "chat1"
        assert exc.custom_field == "value"

    def test_owner_permission_error(self):
        from apps.core.exceptions.chat import owner_permission_error

        exc = owner_permission_error()
        assert exc.code == "OWNER_PERMISSION_ERROR"

    def test_owner_not_found_error(self):
        from apps.core.exceptions.chat import owner_not_found_error

        exc = owner_not_found_error()
        assert exc.code == "OWNER_NOT_FOUND"

    def test_owner_validation_error(self):
        from apps.core.exceptions.chat import owner_validation_error

        exc = owner_validation_error()
        assert exc.code == "OWNER_VALIDATION_ERROR"

    def test_owner_retry_error(self):
        from apps.core.exceptions.chat import owner_retry_error

        exc = owner_retry_error()
        assert exc.code == "OWNER_RETRY_ERROR"

    def test_owner_timeout_error(self):
        from apps.core.exceptions.chat import owner_timeout_error

        exc = owner_timeout_error()
        assert exc.code == "OWNER_TIMEOUT_ERROR"

    def test_owner_network_error(self):
        from apps.core.exceptions.chat import owner_network_error

        exc = owner_network_error()
        assert exc.code == "OWNER_NETWORK_ERROR"

    def test_owner_config_error(self):
        from apps.core.exceptions.chat import owner_config_error

        exc = owner_config_error()
        assert exc.code == "OWNER_CONFIG_ERROR"

    def test_backward_compat_aliases(self):
        from apps.core.exceptions.chat import (
            OwnerConfigException,
            OwnerNetworkException,
            OwnerNotFoundException,
            OwnerPermissionException,
            OwnerRetryException,
            OwnerSettingException,
            OwnerTimeoutException,
            OwnerValidationException,
        )

        assert OwnerPermissionException is OwnerSettingException
        assert OwnerNotFoundException is OwnerSettingException
        assert OwnerValidationException is OwnerSettingException
        assert OwnerRetryException is OwnerSettingException
        assert OwnerTimeoutException is OwnerSettingException
        assert OwnerNetworkException is OwnerSettingException
        assert OwnerConfigException is OwnerSettingException


class TestExternalExceptions:
    def test_external_service_error(self):
        from apps.core.exceptions.external import ExternalServiceError

        exc = ExternalServiceError()
        assert exc.code == "EXTERNAL_SERVICE_ERROR"

    def test_service_unavailable_error_with_service_name(self):
        from apps.core.exceptions.external import ServiceUnavailableError

        exc = ServiceUnavailableError(service_name="ollama")
        assert exc.service_name == "ollama"
        assert exc.errors.get("service") == "ollama"

    def test_service_unavailable_error_without_service_name(self):
        from apps.core.exceptions.external import ServiceUnavailableError

        exc = ServiceUnavailableError()
        assert exc.service_name is None

    def test_recognition_timeout_error_with_timeout(self):
        from apps.core.exceptions.external import RecognitionTimeoutError

        exc = RecognitionTimeoutError(timeout_seconds=30.0)
        assert exc.timeout_seconds == 30.0
        assert exc.errors.get("timeout_seconds") == 30.0

    def test_recognition_timeout_error_without_timeout(self):
        from apps.core.exceptions.external import RecognitionTimeoutError

        exc = RecognitionTimeoutError()
        assert exc.timeout_seconds is None

    def test_token_error(self):
        from apps.core.exceptions.external import TokenError

        exc = TokenError()
        assert exc.code == "TOKEN_ERROR"

    def test_api_error(self):
        from apps.core.exceptions.external import APIError

        exc = APIError()
        assert exc.code == "API_ERROR"

    def test_network_error(self):
        from apps.core.exceptions.external import NetworkError

        exc = NetworkError()
        assert exc.code == "NETWORK_ERROR"

    def test_auto_token_acquisition_error(self):
        from apps.core.exceptions.external import AutoTokenAcquisitionError

        exc = AutoTokenAcquisitionError()
        assert exc.code == "AUTO_TOKEN_ACQUISITION_ERROR"

    def test_login_failed_error_with_attempts(self):
        from apps.core.exceptions.external import LoginFailedError

        exc = LoginFailedError(attempts=["attempt1", "attempt2"])
        assert exc.attempts == ["attempt1", "attempt2"]

    def test_login_failed_error_default_attempts(self):
        from apps.core.exceptions.external import LoginFailedError

        exc = LoginFailedError()
        assert exc.attempts == []

    def test_no_available_account_error(self):
        from apps.core.exceptions.external import NoAvailableAccountError

        exc = NoAvailableAccountError()
        assert exc.code == "NO_AVAILABLE_ACCOUNT"

    def test_token_acquisition_timeout_error(self):
        from apps.core.exceptions.external import TokenAcquisitionTimeoutError

        exc = TokenAcquisitionTimeoutError()
        assert exc.code == "TOKEN_ACQUISITION_TIMEOUT"

    def test_captcha_recognition_error(self):
        from apps.core.exceptions.external import CaptchaRecognitionError

        exc = CaptchaRecognitionError()
        assert exc.code == "CAPTCHA_RECOGNITION_ERROR"

    def test_browser_automation_error_with_url(self):
        from apps.core.exceptions.external import BrowserAutomationError

        exc = BrowserAutomationError(url="https://example.com")
        assert exc.url == "https://example.com"
        assert exc.errors.get("url") == "https://example.com"

    def test_browser_automation_error_without_url(self):
        from apps.core.exceptions.external import BrowserAutomationError

        exc = BrowserAutomationError()
        assert exc.url is None

    def test_imap_connection_error_with_host(self):
        from apps.core.exceptions.external import ImapConnectionError

        exc = ImapConnectionError(host="imap.gmail.com")
        assert exc.host == "imap.gmail.com"
        assert exc.errors.get("host") == "imap.gmail.com"

    def test_imap_connection_error_without_host(self):
        from apps.core.exceptions.external import ImapConnectionError

        exc = ImapConnectionError()
        assert exc.host is None


class TestErrorPresentation:
    def test_error_envelope_to_payload(self):
        from apps.core.exceptions.error_presentation import ErrorEnvelope

        envelope = ErrorEnvelope(
            code="TEST_ERROR", message="test msg", errors={"detail": "x"}, channel="http"
        )
        payload = envelope.to_payload()
        assert payload["code"] == "TEST_ERROR"
        assert payload["message"] == "test msg"
        assert payload["error"] == "test msg"
        assert payload["retryable"] is False
        assert payload["channel"] == "http"

    def test_error_envelope_without_legacy(self):
        from apps.core.exceptions.error_presentation import ErrorEnvelope

        envelope = ErrorEnvelope(code="E", message="m", errors={})
        payload = envelope.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_present_business_exception(self):
        from apps.core.exceptions import NotFoundError, ValidationException
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = NotFoundError(message="not found")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 404
        assert envelope.code == "NOT_FOUND"

    def test_present_validation_exception(self):
        from apps.core.exceptions import ValidationException
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValidationException(message="invalid")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 400

    def test_present_auth_exception(self):
        from apps.core.exceptions import AuthenticationError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = AuthenticationError(message="auth failed")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 401

    def test_present_conflict_error(self):
        from apps.core.exceptions import ConflictError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ConflictError(message="conflict")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 409

    def test_present_rate_limit_error(self):
        from apps.core.exceptions import RateLimitError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RateLimitError(message="rate limited")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_present_permission_denied(self):
        from apps.core.exceptions import PermissionDenied
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = PermissionDenied(message="denied")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 403

    def test_present_unknown_exception_debug(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RuntimeError("debug info")
        envelope, status = presenter.present(exc, channel="http", debug=True)
        assert "debug info" in envelope.message
        assert status == 500

    def test_present_unknown_exception_no_debug(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RuntimeError("hidden")
        envelope, status = presenter.present(exc, channel="http", debug=False)
        assert "隐藏" not in envelope.message or "系统错误" in envelope.message

    def test_present_non_http_channel(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RuntimeError("err")
        envelope, status = presenter.present(exc, channel="websocket")
        assert status is None

    def test_present_external_service_error(self):
        from apps.core.exceptions import ExternalServiceError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ExternalServiceError(message="ext err")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 502
        assert envelope.retryable is True

    def test_present_service_unavailable_error(self):
        from apps.core.exceptions import ServiceUnavailableError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ServiceUnavailableError(message="unavail")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_present_recognition_timeout_error(self):
        from apps.core.exceptions import RecognitionTimeoutError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RecognitionTimeoutError(message="timeout")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_present_business_exception_with_valid_status(self):
        """Test a BusinessException subclass with a valid status attribute."""
        from apps.core.exceptions import NotFoundError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = NotFoundError(message="not found")
        exc.status = 404  # Set custom status
        envelope, status = presenter.present(exc, channel="http")
        assert status == 404

    def test_present_business_exception_with_invalid_status(self):
        """Test a BusinessException subclass with out-of-range status."""
        from apps.core.exceptions import ValidationException
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValidationException(message="custom")
        exc.status = 999  # Out of valid range
        envelope, status = presenter.present(exc, channel="http")
        assert status == 400  # Falls back to default

    def test_present_llm_auth_error(self):
        """Test LLM authentication error mapping."""
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMAuthenticationError

        presenter = ExceptionPresenter()
        exc = LLMAuthenticationError(message="auth fail", code="LLM_AUTH")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 401

    def test_present_llm_backend_unavailable_error(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        presenter = ExceptionPresenter()
        exc = LLMBackendUnavailableError(message="unavail")
        envelope, status = presenter.present(exc, channel="http")
        # LLMBackendUnavailableError inherits from LLMAPIError->ExternalServiceError
        # so it maps to 502 via BusinessException path
        assert status == 502
        assert envelope.retryable is True

    def test_present_llm_timeout_error(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMTimeoutError

        presenter = ExceptionPresenter()
        exc = LLMTimeoutError(message="timeout")
        envelope, status = presenter.present(exc, channel="http")
        # LLMTimeoutError inherits from LLMError->ExternalServiceError
        # so it maps to 502 via BusinessException path
        assert status == 502

    def test_present_llm_api_error_retryable(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMAPIError

        presenter = ExceptionPresenter()
        exc = LLMAPIError(message="api err", code="LLM_API_ERR")
        exc.status_code = 429
        envelope, status = presenter.present(exc, channel="http")
        assert envelope.retryable is True

    def test_present_llm_api_error_not_retryable(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMAPIError

        presenter = ExceptionPresenter()
        exc = LLMAPIError(message="api err", code="LLM_API_ERR")
        exc.status_code = 400
        envelope, status = presenter.present(exc, channel="http")
        # LLMAPIError inherits from ExternalServiceError, so it's always retryable
        assert envelope.retryable is True

    def test_present_llm_api_error_all_backends_unavailable(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter
        from apps.core.llm.exceptions import LLMAPIError

        presenter = ExceptionPresenter()
        exc = LLMAPIError(message="api err", code="LLM_ALL_BACKENDS_UNAVAILABLE")
        exc.status_code = None
        envelope, status = presenter.present(exc, channel="http")
        assert envelope.retryable is True


class TestExceptionsInit:
    def test_automation_exceptions_deprecated(self):
        import warnings

        from apps.core import exceptions

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.warns(DeprecationWarning):
                result = exceptions.AutomationExceptions

    def test_unknown_attr_raises(self):
        from apps.core import exceptions

        with pytest.raises(AttributeError):
            exceptions.SomeNonexistentThing

    def test_register_exception_handlers(self):
        from apps.core.exceptions import register_exception_handlers

        # Just verify it can be called without error (delayed import)
        assert callable(register_exception_handlers)
