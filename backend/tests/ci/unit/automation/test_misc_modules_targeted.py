"""Targeted tests for chat factory, insurance exceptions, text utils, file utils, and other modules."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# ── ChatProviderFactory ───────────────────────────────────────────


class TestChatProviderFactory:
    def test_import(self):
        from apps.automation.services.chat.factory import ChatProviderFactory

        assert ChatProviderFactory is not None

    def test_registered_platforms(self):
        from apps.automation.services.chat.factory import ChatProviderFactory

        registered = ChatProviderFactory.get_registered_platforms()
        assert isinstance(registered, list)

    def test_is_platform_registered(self):
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform

        # Re-register feishu if needed for this test
        if not ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU):
            from apps.automation.services.chat.feishu_provider import FeishuChatProvider

            ChatProviderFactory.register(ChatPlatform.FEISHU, FeishuChatProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU) is True

    def test_unregister_and_restore(self):
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.models.enums import ChatPlatform

        platform = ChatPlatform.FEISHU
        was_registered = ChatProviderFactory.is_platform_registered(platform)
        ChatProviderFactory.unregister(platform)
        assert not ChatProviderFactory.is_platform_registered(platform)
        # Always restore regardless of was_registered
        from apps.automation.services.chat.feishu_provider import FeishuChatProvider

        ChatProviderFactory.register(platform, FeishuChatProvider)

    def test_clear_cache(self):
        from apps.automation.services.chat.factory import ChatProviderFactory

        ChatProviderFactory.clear_cache()


# ── ChatProviderBase ──────────────────────────────────────────────


class TestChatProviderBase:
    def test_base_import(self):
        from apps.automation.services.chat.base import ChatProvider, ChatResult, MessageContent

        assert ChatProvider is not None
        assert ChatResult is not None
        assert MessageContent is not None


# ── Insurance exceptions ──────────────────────────────────────────


class TestInsuranceExceptions:
    def test_token_error(self):
        from plugins.court_automation.preservation_quote.exceptions import TokenError

        exc = TokenError("token无效")
        assert "token" in str(exc).lower()

    def test_api_error(self):
        from plugins.court_automation.preservation_quote.exceptions import APIError

        exc = APIError(message="API调用失败")
        assert "API" in str(exc)

    def test_validation_error(self):
        from plugins.court_automation.preservation_quote.exceptions import ValidationError

        exc = ValidationError(message="验证失败", errors={"field": "error"})
        assert exc.errors == {"field": "error"}

    def test_company_list_empty_error(self):
        from plugins.court_automation.preservation_quote.exceptions import CompanyListEmptyError

        exc = CompanyListEmptyError(message="列表为空")
        assert "空" in str(exc)


# ── Text utils ────────────────────────────────────────────────────


class TestTextUtils:
    def test_extract_case_numbers(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "（2024）京0101民初1234号案件通知"
        result = TextUtils.extract_case_numbers(text)
        assert isinstance(result, list)

    def test_normalize_case_number(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("(2024)京0101民初1234号")
        assert "（" in result
        assert "）" in result

    def test_normalize_empty(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.normalize_case_number("") == ""

    def test_clean_text(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("  hello   world  ")
        assert result == "hello world"

    def test_clean_empty(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.clean_text("") == ""
        assert TextUtils.clean_text(None) == ""


# ── File utils ────────────────────────────────────────────────────


class TestFileUtils:
    def test_validate_not_exists(self):
        from apps.automation.utils.file_utils import FileUtils

        result = FileUtils.validate_file_basic("/nonexistent/file.pdf")
        assert result["valid"] is False
        assert result["error"] == "文件不存在"

    def test_validate_valid(self, tmp_path):
        from apps.automation.utils.file_utils import FileUtils

        f = tmp_path / "test.pdf"
        f.write_bytes(b"test content")
        result = FileUtils.validate_file_basic(str(f))
        assert result["valid"] is True
        assert result["info"]["size"] > 0

    def test_validate_empty(self, tmp_path):
        from apps.automation.utils.file_utils import FileUtils

        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        result = FileUtils.validate_file_basic(str(f))
        assert result["valid"] is False
        assert result["error"] == "文件为空"

    def test_validate_wrong_extension(self, tmp_path):
        from apps.automation.utils.file_utils import FileUtils

        f = tmp_path / "test.txt"
        f.write_bytes(b"content")
        result = FileUtils.validate_file_basic(str(f), expected_extensions=[".pdf"])
        assert result["valid"] is False
        assert "文件类型不匹配" in result["error"]


# ── Concurrency optimizer ─────────────────────────────────────────


class TestConcurrencyOptimizerModule:
    def test_import(self):
        from plugins.court_automation.token.concurrency_optimizer import ConcurrencyOptimizer, ConcurrencyConfig

        assert ConcurrencyOptimizer is not None
        assert ConcurrencyConfig is not None

    def test_concurrency_config_defaults(self):
        from plugins.court_automation.token.concurrency_optimizer import ConcurrencyConfig

        config = ConcurrencyConfig()
        assert config is not None


# ── Cache manager ─────────────────────────────────────────────────


class TestCacheManager:
    def test_import(self):
        from plugins.court_automation.token.cache_manager import TokenCacheManager

        assert TokenCacheManager is not None


# ── Performance monitor ───────────────────────────────────────────


class TestPerformanceMonitor:
    def test_import(self):
        from plugins.court_automation.token.performance_monitor import PerformanceMonitor

        assert PerformanceMonitor is not None


# ── History recorder ──────────────────────────────────────────────


class TestHistoryRecorder:
    def test_import(self):
        from plugins.court_automation.token.history_recorder import TokenHistoryRecorder

        assert TokenHistoryRecorder is not None


# ── AutomationLogger ──────────────────────────────────────────────


class TestAutomationLogger:
    def test_import(self):
        from apps.automation.utils.logging import AutomationLogger

        assert AutomationLogger is not None


# ── GSXT services ─────────────────────────────────────────────────


class TestGsxtServices:
    def test_email_service(self):
        from apps.automation.services.gsxt.gsxt_email_service import GsxtEmailService

        assert GsxtEmailService is not None

    def test_report_service(self):
        from apps.automation.services.gsxt.gsxt_report_service import GsxtReportService

        assert GsxtReportService is not None


# ── Captcha service ───────────────────────────────────────────────


class TestCaptchaService:
    def test_import(self):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        assert CaptchaRecognitionService is not None


# ── Browser context factory ───────────────────────────────────────


class TestBrowserContextFactory:
    def test_import(self):
        from plugins.court_automation.token.browser_context_factory import BrowserContextFactory

        assert BrowserContextFactory is not None


# ── Automation exceptions ─────────────────────────────────────────


class TestAutomationExceptions:
    def test_token_acquisition_error(self):
        from apps.automation.exceptions import AutoTokenAcquisitionError

        exc = AutoTokenAcquisitionError("test")
        assert "test" in str(exc)

    def test_login_failed_error(self):
        from apps.automation.exceptions import LoginFailedError

        assert LoginFailedError is not None

    def test_no_available_account_error(self):
        from apps.automation.exceptions import NoAvailableAccountError

        assert NoAvailableAccountError is not None

    def test_token_acquisition_timeout_error(self):
        from apps.automation.exceptions import TokenAcquisitionTimeoutError

        assert TokenAcquisitionTimeoutError is not None

    def test_captcha_recognition_error(self):
        from apps.automation.exceptions import CaptchaRecognitionError

        assert CaptchaRecognitionError is not None


# ── Management commands imports ───────────────────────────────────


class TestManagementCommands:
    def test_bench_http(self):
        from apps.automation.management.commands.bench_http import Command

        assert Command is not None

    def test_clear_token_cache(self):
        from apps.automation.management.commands.clear_token_cache import Command

        assert Command is not None

    def test_download_ocr_models(self):
        from apps.automation.management.commands.download_ocr_models import Command

        assert Command is not None

    def test_process_pending_tasks(self):
        from apps.automation.management.commands.process_pending_tasks import Command

        assert Command is not None


# ── Ollama modules ────────────────────────────────────────────────


class TestOllamaModules:
    def test_ollama_config(self):
        from apps.automation.services.ai.ollama_config import OllamaConfig

        assert OllamaConfig is not None


# ── Auto namer service adapter ────────────────────────────────────


class TestAutoNamerServiceAdapter:
    def test_import(self):
        from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

        assert AutoNamerServiceAdapter is not None


# ── Chat providers ────────────────────────────────────────────────


class TestChatProviders:
    def test_feishu(self):
        from apps.automation.services.chat.feishu_provider import FeishuChatProvider

        assert FeishuChatProvider is not None


# ── Token usecase ─────────────────────────────────────────────────


class TestAutoLoginUsecase:
    def test_importable(self):
        import apps.automation.usecases.token.auto_login_usecase as m

        assert m is not None


# ── Wiring ────────────────────────────────────────────────────────


class TestWiring:
    def test_import_wiring(self):
        from apps.automation.services import wiring

        assert wiring is not None
