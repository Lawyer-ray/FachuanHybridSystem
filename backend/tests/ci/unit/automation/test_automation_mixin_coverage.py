"""Tests for automation_mixin — coverage for uncovered branches."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.service_locator_mixins.automation_mixin import AutomationServiceLocatorMixin


class ConcreteLocator(AutomationServiceLocatorMixin):
    """Minimal concrete class to test the mixin."""

    _services: dict[str, Any] = {}

    @classmethod
    def get_or_create(cls, name: str, factory: Any) -> Any:
        if name not in cls._services:
            cls._services[name] = factory()
        return cls._services[name]

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._services.get(name)

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        cls._services[name] = service

    @classmethod
    def get_case_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_client_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_lawyer_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_case_number_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_case_chat_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_caselog_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_reminder_service(cls) -> MagicMock:
        return MagicMock()

    @classmethod
    def get_llm_service(cls) -> MagicMock:
        return MagicMock()


class TestAutomationServiceLocatorMixin:
    @pytest.fixture(autouse=True)
    def _reset_services(self) -> Any:
        ConcreteLocator._services = {}
        yield
        ConcreteLocator._services = {}

    def test_get_ai_service(self) -> None:
        with patch("apps.automation.services.ai.ai_service.AIService"):
            result = ConcreteLocator.get_ai_service()
            assert result is not None

    def test_get_ai_service_cached(self) -> None:
        with patch("apps.automation.services.ai.ai_service.AIService"):
            first = ConcreteLocator.get_ai_service()
            second = ConcreteLocator.get_ai_service()
            assert first is second

    def test_get_config_service(self) -> None:
        with patch("apps.automation.services.config_service.AutomationConfigService"):
            result = ConcreteLocator.get_config_service()
            assert result is not None

    def test_get_auto_token_acquisition_service(self) -> None:
        with patch("apps.core.dependencies.build_auto_token_acquisition_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_auto_token_acquisition_service()
            assert result is not None

    def test_get_account_selection_strategy(self) -> None:
        with patch("apps.core.dependencies.build_account_selection_strategy") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_account_selection_strategy()
            assert result is not None

    def test_get_auto_login_service(self) -> None:
        with patch("apps.core.dependencies.build_auto_login_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_auto_login_service()
            assert result is not None

    def test_get_token_service(self) -> None:
        with patch("apps.core.dependencies.build_token_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_token_service()
            assert result is not None

    def test_get_court_token_store_service(self) -> None:
        with patch("apps.core.dependencies.build_court_token_store_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_court_token_store_service()
            assert result is not None

    def test_get_browser_service(self) -> None:
        with patch("apps.core.dependencies.build_browser_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_browser_service()
            assert result is not None

    def test_get_captcha_service(self) -> None:
        with patch("apps.core.dependencies.build_captcha_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_captcha_service()
            assert result is not None

    def test_get_ocr_service(self) -> None:
        with patch("apps.core.dependencies.build_ocr_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_ocr_service()
            assert result is not None

    def test_get_court_document_service(self) -> None:
        with patch("apps.core.dependencies.build_court_document_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_court_document_service()
            assert result is not None

    def test_get_monitor_service(self) -> None:
        with patch("apps.core.dependencies.build_monitor_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_monitor_service()
            assert result is not None

    def test_get_security_service(self) -> None:
        with patch("apps.core.dependencies.build_security_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_security_service()
            assert result is not None

    def test_get_validator_service(self) -> None:
        with patch("apps.core.dependencies.build_validator_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_validator_service()
            assert result is not None

    def test_get_preservation_quote_service(self) -> None:
        with patch("apps.core.dependencies.build_preservation_quote_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_preservation_quote_service()
            assert result is not None

    def test_get_document_processing_service(self) -> None:
        with patch("apps.core.dependencies.build_document_processing_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_document_processing_service()
            assert result is not None

    def test_get_document_processor_service_delegates(self) -> None:
        with patch("apps.core.dependencies.build_document_processing_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_document_processor_service()
            assert result is not None

    def test_get_auto_namer_service(self) -> None:
        with patch("apps.core.dependencies.build_auto_namer_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_auto_namer_service()
            assert result is not None

    def test_get_automation_service(self) -> None:
        with patch("apps.core.dependencies.build_automation_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_automation_service()
            assert result is not None

    def test_get_performance_monitor_service(self) -> None:
        with patch("apps.core.dependencies.build_performance_monitor_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_performance_monitor_service()
            assert result is not None

    def test_get_court_sms_service(self) -> None:
        with patch("apps.core.dependencies.build_court_sms_service_with_deps") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_court_sms_service()
            assert result is not None

    def test_get_court_document_recognition_service(self) -> None:
        with patch("apps.core.dependencies.build_court_document_recognition_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_court_document_recognition_service()
            assert result is not None

    def test_get_court_pleading_signals_service(self) -> None:
        with patch("apps.core.dependencies.build_court_pleading_signals_service") as mock_build:
            mock_build.return_value = MagicMock()
            result = ConcreteLocator.get_court_pleading_signals_service()
            assert result is not None

    def test_get_chat_provider_factory(self) -> None:
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_factory:
            result = ConcreteLocator.get_chat_provider_factory()
            assert result is mock_factory

    def test_build_chat_message_content(self) -> None:
        with patch("apps.automation.services.chat.base.MessageContent") as mock_mc:
            mock_mc.return_value = MagicMock()
            result = ConcreteLocator.build_chat_message_content("title", "text", "file.pdf")
            mock_mc.assert_called_once_with(title="title", text="text", file_path="file.pdf")
            assert result is not None

    def test_build_chat_message_content_no_file(self) -> None:
        with patch("apps.automation.services.chat.base.MessageContent") as mock_mc:
            mock_mc.return_value = MagicMock()
            result = ConcreteLocator.build_chat_message_content("title", "text")
            mock_mc.assert_called_once_with(title="title", text="text", file_path=None)
            assert result is not None

    def test_get_task_service(self) -> None:
        with patch("apps.automation.models.ScraperTask") as mock_task:
            result = ConcreteLocator.get_task_service()
            assert result is mock_task
