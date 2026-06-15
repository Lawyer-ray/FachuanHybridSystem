"""Tests for error_presentation, throttling, chat_provider_facade, dashboard_service, and other modules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions.error_presentation import ErrorEnvelope, ExceptionPresenter
from apps.core.exceptions import (
    BusinessError,
    BusinessException,
    NotFoundError,
    ValidationException,
    ForbiddenError,
    RateLimitError,
    ExternalServiceError,
    ConflictError,
    PermissionDenied,
    AuthenticationError,
    ServiceUnavailableError,
    RecognitionTimeoutError,
)
from apps.cases.services.chat.provider_facade import ChatProviderFacade
from apps.core.models.enums import ChatPlatform


# ---------------------------------------------------------------------------
# ErrorEnvelope
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    def test_to_payload_full(self):
        env = ErrorEnvelope(code="TEST", message="err", errors={"k": "v"}, retryable=True, channel="http")
        payload = env.to_payload()
        assert payload["code"] == "TEST"
        assert payload["message"] == "err"
        assert payload["errors"] == {"k": "v"}
        assert payload["retryable"] is True
        assert payload["channel"] == "http"
        assert payload["error"] == "err"

    def test_to_payload_no_legacy_error(self):
        env = ErrorEnvelope(code="X", message="m", errors={})
        payload = env.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_to_payload_ws_channel(self):
        env = ErrorEnvelope(code="X", message="m", errors={}, channel="ws")
        payload = env.to_payload()
        assert payload["channel"] == "ws"

    def test_to_payload_empty_errors(self):
        env = ErrorEnvelope(code="X", message="m", errors={})
        payload = env.to_payload()
        assert payload["errors"] == {}


# ---------------------------------------------------------------------------
# ExceptionPresenter
# ---------------------------------------------------------------------------


class TestExceptionPresenter:
    def setup_method(self):
        self.presenter = ExceptionPresenter()

    def test_present_business_exception_not_found(self):
        exc = NotFoundError("not found")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 404
        assert envelope.code == exc.code

    def test_present_business_exception_validation(self):
        exc = ValidationException("bad input")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 400

    def test_present_business_exception_rate_limit(self):
        exc = RateLimitError("too many")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_present_business_exception_forbidden(self):
        exc = ForbiddenError("no access")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 403

    def test_present_business_exception_conflict(self):
        exc = ConflictError("conflict")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 409

    def test_present_business_exception_service_unavailable(self):
        exc = ServiceUnavailableError("down")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 503
        assert envelope.retryable is True

    def test_present_business_exception_timeout(self):
        exc = RecognitionTimeoutError("timeout")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 504
        assert envelope.retryable is True

    def test_present_business_exception_external(self):
        exc = ExternalServiceError("external")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 502

    def test_present_generic_exception_debug(self):
        exc = RuntimeError("boom")
        envelope, status = self.presenter.present(exc, channel="http", debug=True)
        assert status == 500
        assert "boom" in envelope.message

    def test_present_generic_exception_no_debug(self):
        exc = RuntimeError("boom")
        envelope, status = self.presenter.present(exc, channel="http", debug=False)
        assert status == 500
        assert envelope.message == "系统错误,请稍后重试"

    def test_present_ws_channel_returns_none_status(self):
        exc = RuntimeError("boom")
        envelope, status = self.presenter.present(exc, channel="ws", debug=False)
        assert status is None

    def test_present_llm_auth_error(self):
        from apps.core.llm.exceptions import LLMAuthenticationError

        exc = LLMAuthenticationError("auth fail")
        envelope, status = self.presenter.present(exc, channel="http")
        assert status == 401

    def test_present_llm_backend_unavailable_error(self):
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        exc = LLMBackendUnavailableError("all unavailable")
        envelope, status = self.presenter.present(exc, channel="http")
        # LLMBackendUnavailableError inherits from ExternalServiceError -> 502
        assert status == 502

    def test_present_llm_timeout_error(self):
        from apps.core.llm.exceptions import LLMTimeoutError

        exc = LLMTimeoutError("timed out")
        envelope, status = self.presenter.present(exc, channel="http")
        # LLMTimeoutError -> mapped to RecognitionTimeoutError -> ExternalServiceError chain -> 502
        assert status == 502

    def test_present_llm_api_error_retryable(self):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("api err", status_code=502)
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.retryable is True

    def test_present_llm_api_error_retryable_status_code(self):
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError("api err", status_code=429)
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.retryable is True

    def test_present_llm_api_error_retryable_via_inheritance(self):
        from apps.core.llm.exceptions import LLMAPIError

        # LLMAPIError inherits ExternalServiceError, which is always retryable in the business exception handler
        exc = LLMAPIError("api err", status_code=400)
        envelope, status = self.presenter.present(exc, channel="http")
        assert envelope.retryable is True

    def test_retryable_for_business_exception(self):
        assert self.presenter._retryable_for_business_exception(RateLimitError("x")) is True
        assert self.presenter._retryable_for_business_exception(NotFoundError("x")) is False


# ---------------------------------------------------------------------------
# ChatProviderFacade
# ---------------------------------------------------------------------------


class TestChatProviderFacade:
    def test_get_provider_for_creation_success(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.get_provider_for_creation(platform=ChatPlatform.FEISHU)
        assert result == mock_provider

    def test_get_provider_for_creation_factory_error(self):
        mock_factory = MagicMock()
        mock_factory.get_provider.side_effect = RuntimeError("no provider")
        facade = ChatProviderFacade(factory=mock_factory)
        with pytest.raises(Exception):
            facade.get_provider_for_creation(platform=ChatPlatform.FEISHU)

    def test_get_provider_for_creation_not_available(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        with pytest.raises(Exception):
            facade.get_provider_for_creation(platform=ChatPlatform.FEISHU)

    def test_get_provider_for_messaging_success(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.get_provider_for_messaging(platform=ChatPlatform.FEISHU, chat_id="123")
        assert result == mock_provider

    def test_get_provider_for_messaging_factory_error(self):
        mock_factory = MagicMock()
        mock_factory.get_provider.side_effect = RuntimeError("no provider")
        facade = ChatProviderFacade(factory=mock_factory)
        with pytest.raises(Exception):
            facade.get_provider_for_messaging(platform=ChatPlatform.FEISHU, chat_id="123")

    def test_try_get_chat_name_success(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.chat_name = "Test Chat"
        mock_provider.get_chat_info.return_value = mock_result
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.try_get_chat_name(platform=ChatPlatform.FEISHU, chat_id="123")
        assert result == "Test Chat"

    def test_try_get_chat_name_not_available(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.try_get_chat_name(platform=ChatPlatform.FEISHU, chat_id="123")
        assert result is None

    def test_try_get_chat_name_exception(self):
        mock_factory = MagicMock()
        mock_factory.get_provider.side_effect = RuntimeError("error")
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.try_get_chat_name(platform=ChatPlatform.FEISHU, chat_id="123")
        assert result is None

    def test_try_get_chat_name_no_success(self):
        mock_factory = MagicMock()
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.chat_name = None
        mock_provider.get_chat_info.return_value = mock_result
        mock_factory.get_provider.return_value = mock_provider
        facade = ChatProviderFacade(factory=mock_factory)
        result = facade.try_get_chat_name(platform=ChatPlatform.FEISHU, chat_id="123")
        assert result is None

    def test_create_chat(self):
        mock_factory = MagicMock()
        facade = ChatProviderFacade(factory=mock_factory)
        mock_provider = MagicMock()
        facade.create_chat(provider=mock_provider, chat_name="Test", owner_id="1")
        mock_provider.create_chat.assert_called_once_with("Test", "1")


# ---------------------------------------------------------------------------
# InvoiceRecognitionService _validate_file
# ---------------------------------------------------------------------------


class TestInvoiceRecognitionServiceValidation:
    def _make_service(self):
        from apps.invoice_recognition.services.invoice_recognition_service import InvoiceRecognitionService

        return InvoiceRecognitionService(
            ocr_service=MagicMock(),
            pdf_extractor=MagicMock(),
            parser=MagicMock(),
        )

    def test_validate_file_bad_extension(self):
        svc = self._make_service()
        mock_file = MagicMock()
        mock_file.name = "test.exe"
        mock_file.size = 1000
        with pytest.raises(Exception):
            svc._validate_file(mock_file)

    def test_validate_file_too_large(self):
        svc = self._make_service()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.size = 30 * 1024 * 1024  # 30 MB
        with pytest.raises(Exception):
            svc._validate_file(mock_file)

    def test_validate_file_valid(self):
        svc = self._make_service()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.size = 1000
        svc._validate_file(mock_file)  # Should not raise

    def test_validate_file_no_name(self):
        svc = self._make_service()
        mock_file = MagicMock()
        mock_file.name = None
        mock_file.size = 1000
        with pytest.raises(Exception):
            svc._validate_file(mock_file)

    def test_get_task_status(self):
        svc = self._make_service()
        with patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecognitionTask") as MockTask:
            mock_task = MagicMock()
            mock_task.id = 1
            mock_task.name = "Task 1"
            mock_task.status = "completed"
            mock_task.created_at = datetime(2024, 1, 1)
            mock_task.finished_at = datetime(2024, 1, 2)
            mock_task.records.all.return_value = []
            MockTask.objects.prefetch_related.return_value.get.return_value = mock_task
            result = svc.get_task_status(1)
            assert result["task"]["id"] == 1
            assert result["records"] == []

    def test_get_total_amount(self):
        svc = self._make_service()
        with patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord") as MockRecord:
            MockRecord.objects.filter.return_value.aggregate.return_value = {"total": Decimal("100.00")}
            result = svc.get_total_amount(1)
            assert result == Decimal("100.00")

    def test_get_category_subtotal(self):
        svc = self._make_service()
        with patch("apps.invoice_recognition.services.invoice_recognition_service.InvoiceRecord") as MockRecord:
            MockRecord.objects.filter.return_value.aggregate.return_value = {"total": Decimal("50.00")}
            result = svc.get_category_subtotal(1, "invoice")
            assert result == Decimal("50.00")


# ---------------------------------------------------------------------------
# LLM backends __init__
# ---------------------------------------------------------------------------


class TestLLMBackendsInit:
    def test_import_backends(self):
        from apps.core.llm.backends import (
            ILLMBackend,
            LLMResponse,
            LLMStreamChunk,
            LLMUsage,
            OllamaBackend,
        )

        assert ILLMBackend is not None
        assert OllamaBackend is not None

    def test_llm_stream_chunk_default(self):
        from apps.core.llm.backends import LLMStreamChunk

        chunk = LLMStreamChunk()
        assert chunk.content == ""
        assert chunk.model == ""

    def test_llm_usage_default(self):
        from apps.core.llm.backends import LLMUsage

        usage = LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert usage.prompt_tokens == 10
        assert usage.total_tokens == 30
