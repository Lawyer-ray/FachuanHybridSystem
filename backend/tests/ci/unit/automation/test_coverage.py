"""automation 模块单元测试（token_service, history_recorder, auto_login_service, owner_config_manager, logging_mixin, captcha, base_scraper）。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ── token_service (TokenService) ────────────────────────────────


class TestTokenService:
    @patch("plugins.court_automation.login.token_service.cache")
    def test_get_cache_key(self, mock_cache: MagicMock) -> None:
        from apps.automation.services.scraper.core.token_service import TokenService

        svc = TokenService()
        with patch("apps.core.infrastructure.cache.CacheKeys") as mock_keys:
            mock_keys.court_token.return_value = "prefix:site:acct"
            key = svc._get_cache_key("site", "acct")
            assert key == "prefix:site:acct"

    @patch("plugins.court_automation.login.token_service.cache")
    @patch("apps.automation.models.CourtToken")
    def test_get_token_from_redis(self, mock_ct: MagicMock, mock_cache: MagicMock) -> None:
        from apps.automation.services.scraper.core.token_service import TokenService

        mock_cache.get.return_value = "redis_token"
        with patch("apps.core.infrastructure.cache.CacheKeys") as mock_keys:
            mock_keys.court_token.return_value = "key"
            svc = TokenService()
            result = svc.get_token("site", "acct")
            assert result == "redis_token"

    @patch("plugins.court_automation.login.token_service.cache")
    def test_get_token_redis_miss_db_miss(self, mock_cache: MagicMock) -> None:
        from apps.automation.services.scraper.core.token_service import TokenService

        mock_cache.get.return_value = None
        with patch("apps.core.infrastructure.cache.CacheKeys") as mock_keys:
            mock_keys.court_token.return_value = "key"
            with patch("apps.automation.models.CourtToken") as mock_ct:
                mock_ct.objects.get.side_effect = mock_ct.DoesNotExist
                svc = TokenService()
                result = svc.get_token("site", "acct")
                assert result is None

    @patch("plugins.court_automation.login.token_service.cache")
    def test_delete_token(self, mock_cache: MagicMock) -> None:
        from apps.automation.services.scraper.core.token_service import TokenService

        with patch("apps.core.infrastructure.cache.CacheKeys") as mock_keys:
            mock_keys.court_token.return_value = "key"
            with patch("apps.automation.models.CourtToken") as mock_ct:
                mock_ct.objects.filter.return_value.delete.return_value = (1, {})
                svc = TokenService()
                svc.delete_token("site", "acct")
                mock_cache.delete.assert_called_once()


class TestTokenServiceAdapter:
    def test_init(self) -> None:
        from apps.automation.services.scraper.core.token_service import TokenServiceAdapter, TokenService

        svc = MagicMock(spec=TokenService)
        adapter = TokenServiceAdapter(service=svc, default_account="test")
        assert adapter._default_account == "test"

    def test_service_lazy_load(self) -> None:
        from apps.automation.services.scraper.core.token_service import TokenServiceAdapter

        adapter = TokenServiceAdapter()
        assert adapter._service is None


# ── history_recorder ────────────────────────────────────────────


class TestTokenHistoryRecorder:
    def test_init(self) -> None:
        from plugins.court_automation.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        assert recorder._db_service is None

    def test_db_service_lazy_load(self) -> None:
        from plugins.court_automation.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        svc = recorder.db_service
        assert svc is not None

    @pytest.mark.asyncio
    async def test_cleanup_old_records_exception(self) -> None:
        from plugins.court_automation.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        with patch("apps.automation.models.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = await recorder.cleanup_old_records(days=30)
            assert result == 0


# ── auto_login_service ──────────────────────────────────────────


class TestRetryConfig:
    def test_defaults(self) -> None:
        from plugins.court_automation.token.auto_login_service import RetryConfig

        cfg = RetryConfig()
        assert cfg.max_network_retries == 3
        assert cfg.max_captcha_retries == 3
        assert cfg.login_timeout == 60.0


class TestAutoLoginService:
    def test_init(self) -> None:
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        svc = AutoLoginService()
        assert svc.retry_config.max_network_retries == 3
        assert svc._login_attempts == []

    def test_get_login_attempts(self) -> None:
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        svc = AutoLoginService()
        assert svc.get_login_attempts() == []

    def test_clear_login_attempts(self) -> None:
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        svc = AutoLoginService()
        svc._login_attempts.append(MagicMock())
        svc.clear_login_attempts()
        assert svc._login_attempts == []

    def test_browser_service_lazy_load(self) -> None:
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        svc = AutoLoginService()
        assert svc._browser_service is None

    @pytest.mark.asyncio
    async def test_login_and_get_token_delegates_to_usecase(self) -> None:
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        mock_usecase = MagicMock()
        mock_usecase.execute = AsyncMock(return_value="token123")
        credential = MagicMock()
        credential.site_name = "test"
        credential.account = "acct"

        svc = AutoLoginService(usecase=mock_usecase)
        result = await svc.login_and_get_token(credential)
        assert result == "token123"


# ── owner_config_manager ────────────────────────────────────────


class TestOwnerConfigManager:
    @patch("apps.automation.services.chat.owner_config_manager.OwnerConfigManager._load_config")
    @patch("apps.automation.services.chat.owner_config_manager.OwnerConfigManager._load_default_owner_id")
    def test_init(self, mock_load_default: MagicMock, mock_load_config: MagicMock) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mock_load_config.return_value = {"TEST_MODE": False, "OWNER_VALIDATION_ENABLED": True}
        mock_load_default.return_value = None
        mgr = OwnerConfigManager()
        assert mgr._config is not None

    def test_validate_owner_id_empty(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        assert mgr.validate_owner_id("") is False
        assert mgr.validate_owner_id(None) is False  # type: ignore[arg-type]

    def test_validate_owner_id_invalid(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        assert mgr.validate_owner_id("invalid_id") is False

    def test_validate_owner_id_open_id(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        valid_id = "ou_" + "a" * 32
        assert mgr.validate_owner_id(valid_id) is True

    def test_validate_owner_id_union_id(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        valid_id = "on_" + "b" * 32
        assert mgr.validate_owner_id(valid_id) is True

    def test_get_effective_owner_id_specified_valid(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        mgr._default_owner_id = None
        valid_id = "ou_" + "a" * 32
        assert mgr.get_effective_owner_id(valid_id) == valid_id

    def test_get_effective_owner_id_specified_invalid_fallback(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        mgr._default_owner_id = "ou_" + "b" * 32
        assert mgr.get_effective_owner_id("invalid") == "ou_" + "b" * 32

    def test_get_effective_owner_id_none_returns_default(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        mgr._default_owner_id = "ou_" + "c" * 32
        assert mgr.get_effective_owner_id(None) == "ou_" + "c" * 32

    def test_get_effective_owner_id_all_none(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        mgr._default_owner_id = None
        assert mgr.get_effective_owner_id(None) is None

    def test_is_test_environment(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"TEST_MODE": True}
        assert mgr.is_test_environment() is True

    def test_is_validation_enabled(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": False}
        assert mgr.is_validation_enabled() is False

    def test_is_retry_enabled(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_RETRY_ENABLED": True}
        assert mgr.is_retry_enabled() is True

    def test_get_max_retries(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_MAX_RETRIES": 5}
        assert mgr.get_max_retries() == 5

    def test_handle_empty_owner_id_none(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {}
        mgr._default_owner_id = "ou_" + "d" * 32
        assert mgr.handle_empty_owner_id(None) == "ou_" + "d" * 32

    def test_handle_empty_owner_id_empty_string(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {}
        mgr._default_owner_id = "ou_" + "e" * 32
        assert mgr.handle_empty_owner_id("") == "ou_" + "e" * 32

    def test_handle_empty_owner_id_valid(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {}
        mgr._default_owner_id = None
        assert mgr.handle_empty_owner_id("  valid_id  ") == "valid_id"

    def test_get_config_summary(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"TEST_MODE": False, "OWNER_VALIDATION_ENABLED": True, "OWNER_RETRY_ENABLED": True, "OWNER_MAX_RETRIES": 3}
        mgr._default_owner_id = "ou_" + "f" * 32
        summary = mgr.get_config_summary()
        assert summary["has_default_owner"] is True
        assert summary["test_mode"] is False

    def test_validate_owner_id_strict_raises(self) -> None:
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager
        from apps.core.exceptions import ValidationException

        mgr = object.__new__(OwnerConfigManager)
        mgr._config = {"OWNER_VALIDATION_ENABLED": True}
        with pytest.raises(ValidationException):
            mgr.validate_owner_id_strict("invalid")


# ── logging mixin ───────────────────────────────────────────────


class TestApiLoggingMixin:
    def test_log_performance_metrics_collection_start(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_performance_metrics_collection_start("cpu")

    def test_log_performance_metrics_collection_success(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_performance_metrics_collection_success("cpu", 10, 1.5)

    def test_log_performance_metrics_collection_failed(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_performance_metrics_collection_failed("cpu", "err", 1.5)

    def test_log_performance_metric_recorded(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_performance_metric_recorded("cpu_usage", 75.5)

    def test_log_admin_operation_start(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_admin_operation_start("export", user_id=1)

    def test_log_admin_operation_success(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_admin_operation_success("export", 10, 2.5, user_id=1)

    def test_log_admin_operation_failed(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_admin_operation_failed("export", "err", 2.5, user_id=1)

    def test_log_business_operation(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_business_operation("create", "contract", resource_id=1, user_id=1)

    def test_log_business_operation_failure(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_business_operation("create", "contract", success=False)

    def test_log_cross_module_call(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_cross_module_call("module_a", "module_b", "Svc", "method")

    def test_log_document_api_request_start(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_api_request_start("get_docs", page_num=1, page_size=10)

    def test_log_document_api_request_success(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_api_request_success("get_docs", 200, 1.5, document_count=10)

    def test_log_document_api_request_failed(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_api_request_failed("get_docs", "timeout", 30.0)

    def test_log_document_query_statistics(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_query_statistics(100, 80, 10, 10)

    def test_log_document_download_start(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_download_start("判决书", url="https://example.com/doc")

    def test_log_document_download_success(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_download_success("判决书", 1024, 1.5)

    def test_log_document_download_failed(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_document_download_failed("判决书", "err", 1.5)

    def test_log_fallback_triggered(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_fallback_triggered("api", "browser", "timeout")

    def test_log_api_error_detail(self) -> None:
        from apps.automation.utils._logging_api_mixin import ApiLoggingMixin

        ApiLoggingMixin.log_api_error_detail(
            "get_docs", "TimeoutError", "request timed out",
            stack_trace="trace...", request_params={"page": 1},
            response_data={"code": 500}
        )


# ── captcha recognition ─────────────────────────────────────────


class TestCaptchaResult:
    def test_creation(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaResult

        r = CaptchaResult(success=True, text="abc", processing_time=1.0, error=None)
        assert r.success is True
        assert r.text == "abc"


class TestCaptchaRecognitionService:
    def test_init_defaults(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        assert svc.MAX_FILE_SIZE == 5 * 1024 * 1024
        assert "PNG" in svc.SUPPORTED_FORMATS

    def test_init_with_config(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService(config={"max_file_size": 1024})
        assert svc.MAX_FILE_SIZE == 1024

    def test_decode_base64_image(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        img_b64 = "data:image/png;base64," + "dGVzdA=="
        result = svc._decode_base64_image(img_b64)
        assert result == b"test"

    def test_decode_base64_image_no_prefix(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        result = svc._decode_base64_image("dGVzdA==")
        assert result == b"test"

    def test_decode_base64_image_invalid(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        with pytest.raises(ValueError):
            svc._decode_base64_image("not_valid_base64!!!")

    def test_validate_image_size_ok(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        svc._validate_image_size(b"x" * 100)  # should not raise

    def test_validate_image_size_too_large(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        with pytest.raises(ValueError, match="超过"):
            svc._validate_image_size(b"x" * (6 * 1024 * 1024))

    def test_validate_image_format_invalid(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        with pytest.raises(ValueError):
            svc._validate_image_format(b"not an image")

    def test_recognize_from_base64_empty(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64("")
        assert result.success is False
        assert result.error == "图片数据不能为空"


class TestCaptchaServiceAdapter:
    def test_init(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter

        adapter = CaptchaServiceAdapter()
        assert adapter._service is None

    def test_recognize_from_base64(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import (
            CaptchaServiceAdapter,
            CaptchaRecognitionService,
            CaptchaResult,
        )

        mock_service = MagicMock(spec=CaptchaRecognitionService)
        mock_service.recognize_from_base64.return_value = CaptchaResult(
            success=True, text="abc", processing_time=0.5, error=None
        )
        adapter = CaptchaServiceAdapter(service=mock_service)
        result = adapter.recognize_from_base64("dGVzdA==")
        assert result.text == "abc"


# ── base scraper ────────────────────────────────────────────────


class TestBaseScraper:
    def test_is_playwright_available(self) -> None:
        from apps.automation.services.scraper.scrapers.base import is_playwright_available

        # Just test it returns a bool
        result = is_playwright_available()
        assert isinstance(result, bool)


# ── auto_token_acquisition_service ──────────────────────────────


class TestAutoTokenAcquisitionService:
    def test_get_statistics(self) -> None:
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        svc = AutoTokenAcquisitionService()
        stats = svc.get_statistics()
        assert stats["acquisition_count"] == 0
        assert stats["success_count"] == 0

    def test_reset_statistics(self) -> None:
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        svc = AutoTokenAcquisitionService()
        svc._acquisition_count = 5
        svc.reset_statistics()
        assert svc._acquisition_count == 0

    def test_clear_locks(self) -> None:
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        AutoTokenAcquisitionService._active_acquisitions.add("test")
        AutoTokenAcquisitionService.clear_locks()
        assert len(AutoTokenAcquisitionService._active_acquisitions) == 0

    @pytest.mark.asyncio
    async def test_acquire_token_empty_site_name(self) -> None:
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        from apps.core.exceptions import ValidationException

        svc = AutoTokenAcquisitionService()
        with pytest.raises(ValidationException):
            await svc.acquire_token_if_needed("")
