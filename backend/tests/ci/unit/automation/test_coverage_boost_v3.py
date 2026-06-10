"""Tests for concurrency optimizer, token services, admin services, and API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest


# ── concurrency optimizer ────────────────────────────────────────


class TestConcurrencyOptimizer:
    def test_init(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        assert opt is not None

    def test_check_concurrency_limits(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        result = opt._check_concurrency_limits("test_site", "test_account")
        assert isinstance(result, bool)

    def test_update_resource_usage_increment(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        opt._update_resource_usage("test_site", "test_account", increment=True)
        opt._update_resource_usage("test_site", "test_account", increment=False)

    def test_wake_next_eligible(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        opt._wake_next_eligible()

    def test_acquire_resource_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        result = asyncio.run(opt.acquire_resource("test-id", "test_site", "test_account"))
        assert isinstance(result, bool)

    def test_release_resource_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        asyncio.run(opt.acquire_resource("test-id", "test_site", "test_account"))
        asyncio.run(opt.release_resource("test-id", "test_site", "test_account"))

    def test_get_resource_usage_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        result = asyncio.run(opt.get_resource_usage())
        assert isinstance(result, dict)

    def test_optimize_concurrency_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        result = asyncio.run(opt.optimize_concurrency())
        assert isinstance(result, dict)

    def test_cleanup_resources_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        asyncio.run(opt.cleanup_resources())

    def test_get_lock_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        lock = asyncio.run(opt._get_lock("test_key"))
        assert lock is not None

    def test_get_lock_returns_existing_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        lock1 = asyncio.run(opt._get_lock("test_key"))
        lock2 = asyncio.run(opt._get_lock("test_key"))
        assert lock1 is lock2

    def test_cleanup_expired_locks_async(self) -> None:
        from apps.automation.services.token.concurrency_optimizer import ConcurrencyOptimizer

        opt = ConcurrencyOptimizer()
        asyncio.run(opt._cleanup_expired_locks())


# ── history recorder (async with asyncio.run) ────────────────────


class TestHistoryRecorderAsync:
    @pytest.mark.django_db
    def test_cleanup_old_records(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        result = asyncio.run(recorder.cleanup_old_records(days=30))
        assert isinstance(result, int)

    @pytest.mark.django_db
    def test_get_recent_statistics(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        result = asyncio.run(recorder.get_recent_statistics(hours=24))
        assert "total_acquisitions" in result
        assert "success_rate" in result

    @pytest.mark.django_db
    def test_get_recent_statistics_with_site_filter(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        result = asyncio.run(recorder.get_recent_statistics(site_name="court_zxfw", hours=24))
        assert "total_acquisitions" in result

    @pytest.mark.django_db
    def test_get_account_performance(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        result = asyncio.run(
            recorder.get_account_performance(account="test", site_name="court_zxfw", days=7)
        )
        assert "account" in result
        assert result["account"] == "test"
        assert "success_rate" in result

    @pytest.mark.django_db
    def test_get_account_performance_no_data(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        result = asyncio.run(
            recorder.get_account_performance(
                account="nonexistent_user", site_name="nonexistent_site", days=1
            )
        )
        assert result["total_attempts"] == 0
        assert result["success_rate"] == 0

    def test_cleanup_old_records_exception(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        with patch("apps.automation.models.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = asyncio.run(recorder.cleanup_old_records(days=30))
            assert result == 0

    def test_get_recent_statistics_exception(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        with patch("apps.automation.models.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = asyncio.run(recorder.get_recent_statistics())
            assert result["total_acquisitions"] == 0

    def test_get_account_performance_exception(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder

        recorder = TokenHistoryRecorder()
        with patch("apps.automation.models.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = asyncio.run(
                recorder.get_account_performance(account="test", site_name="site")
            )
            assert result["total_attempts"] == 0

    @pytest.mark.django_db
    def test_record_acquisition_history_success(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult, LoginAttemptResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=True,
            token="abc123def456",
            acquisition_method="auto_login",
            total_duration=5.0,
            login_attempts=[
                LoginAttemptResult(
                    success=True,
                    token="abc123",
                    account="test_user",
                    error_message=None,
                    attempt_duration=3.0,
                    retry_count=0,
                ),
            ],
            error_details=None,
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-123",
                site_name="court_zxfw",
                account="test_user",
                credential_id=1,
                result=result,
            )
        )

    @pytest.mark.django_db
    def test_record_acquisition_history_failure_timeout(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult, LoginAttemptResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=30.0,
            login_attempts=[
                LoginAttemptResult(
                    success=False,
                    token=None,
                    account="test_user",
                    error_message="captcha timeout error",
                    attempt_duration=30.0,
                    retry_count=1,
                ),
            ],
            error_details={"error_type": "timeout", "message": "请求超时"},
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-456",
                site_name="court_zxfw",
                account="test_user",
                credential_id=None,
                result=result,
            )
        )

    @pytest.mark.django_db
    def test_record_acquisition_history_failure_network(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult, LoginAttemptResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=10.0,
            login_attempts=[
                LoginAttemptResult(
                    success=False,
                    token=None,
                    account="test_user",
                    error_message="network connection error",
                    attempt_duration=10.0,
                    retry_count=2,
                ),
            ],
            error_details={"error_type": "network", "message": "网络错误"},
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-789",
                site_name="court_zxfw",
                account="test_user",
                credential_id=None,
                result=result,
            )
        )

    @pytest.mark.django_db
    def test_record_acquisition_history_failure_captcha(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult, LoginAttemptResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=15.0,
            login_attempts=[
                LoginAttemptResult(
                    success=False,
                    token=None,
                    account="test_user",
                    error_message="captcha recognition failed",
                    attempt_duration=15.0,
                    retry_count=3,
                ),
            ],
            error_details={"error_type": "captcha", "message": "验证码识别失败"},
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-captcha",
                site_name="court_zxfw",
                account="test_user",
                credential_id=None,
                result=result,
            )
        )

    @pytest.mark.django_db
    def test_record_acquisition_history_failure_credential(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=2.0,
            login_attempts=[],
            error_details={"error_type": "credential", "message": "凭证错误"},
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-cred",
                site_name="court_zxfw",
                account="test_user",
                credential_id=None,
                result=result,
            )
        )

    @pytest.mark.django_db
    def test_record_acquisition_history_failure_general(self) -> None:
        from apps.automation.services.token.history_recorder import TokenHistoryRecorder
        from apps.core.dto.auth import TokenAcquisitionResult

        recorder = TokenHistoryRecorder()
        result = TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=5.0,
            login_attempts=[],
            error_details={"error_type": "unknown", "message": "未知错误"},
        )
        asyncio.run(
            recorder.record_acquisition_history(
                acquisition_id="test-general",
                site_name="court_zxfw",
                account="test_user",
                credential_id=None,
                result=result,
            )
        )


# ── auto login service (async) ───────────────────────────────────


class TestAutoLoginServiceAsync:
    def test_login_and_get_token_delegates_to_usecase(self) -> None:
        from apps.automation.services.token.auto_login_service import AutoLoginService

        mock_usecase = MagicMock()
        mock_usecase.execute = AsyncMock(return_value="token123")
        credential = MagicMock()
        credential.site_name = "test"
        credential.account = "acct"

        svc = AutoLoginService(usecase=mock_usecase)
        result = asyncio.run(svc.login_and_get_token(credential))
        assert result == "token123"


# ── auto token acquisition service (async) ───────────────────────


class TestAutoTokenAcquisitionAsync:
    def test_acquire_token_empty_site_name(self) -> None:
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        from apps.core.exceptions import ValidationException

        svc = AutoTokenAcquisitionService()
        with pytest.raises(ValidationException):
            asyncio.run(svc.acquire_token_if_needed(""))


# ── account selection strategy ────────────────────────────────────


class TestAccountSelectionStrategy:
    def test_class_exists(self) -> None:
        from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy

        assert AccountSelectionStrategy is not None

    def test_init(self) -> None:
        from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy

        strategy = AccountSelectionStrategy()
        assert strategy is not None


# ── login handler ────────────────────────────────────────────────


class TestLoginHandler:
    def test_class_exists(self) -> None:
        from apps.automation.services.token._login_handler import LoginHandler

        assert LoginHandler is not None


# ── admin services ───────────────────────────────────────────────


class TestAdminServices:
    def test_court_document_admin_service_class(self) -> None:
        from apps.automation.services.admin.court_document_admin_service import (
            CourtDocumentAdminService,
        )

        assert CourtDocumentAdminService is not None

    def test_preservation_quote_admin_service_class(self) -> None:
        from apps.automation.services.admin.preservation_quote_admin_service import (
            PreservationQuoteAdminService,
        )

        assert PreservationQuoteAdminService is not None

    def test_token_acquisition_history_admin_service_class(self) -> None:
        from apps.automation.services.admin.token_acquisition_history_admin_service import (
            TokenAcquisitionHistoryAdminService,
        )

        assert TokenAcquisitionHistoryAdminService is not None

    def test_document_delivery_schedule_admin_service_class(self) -> None:
        from apps.automation.services.admin.document_delivery_schedule_admin_service import (
            DocumentDeliveryScheduleAdminService,
        )

        assert DocumentDeliveryScheduleAdminService is not None


# ── wiring modules ───────────────────────────────────────────────


class TestWiringModules:
    def test_document_delivery_wiring(self) -> None:
        from apps.automation.services.document_delivery.wiring import (
            build_document_delivery_coordinator,
        )

        assert callable(build_document_delivery_coordinator)

    def test_main_wiring(self) -> None:
        from apps.automation.services.wiring import get_baoquan_token_service

        assert callable(get_baoquan_token_service)


# ── SMS services extended ────────────────────────────────────────


class TestSMSServicesExtended:
    def test_court_sms_repository_class(self) -> None:
        from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

        assert CourtSMSRepository is not None

    def test_sms_parser_service_class(self) -> None:
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        assert SMSParserService is not None

    def test_court_sms_service_class(self) -> None:
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        assert CourtSMSService is not None

    def test_case_matcher_class(self) -> None:
        from apps.automation.services.sms.case_matcher import CaseMatcher

        assert CaseMatcher is not None


# ── insurance services extended ──────────────────────────────────


class TestInsuranceServicesExtended:
    def test_preservation_quote_service_class(self) -> None:
        from apps.automation.services.insurance.preservation_quote_service import (
            PreservationQuoteService,
        )

        assert PreservationQuoteService is not None

    def test_preservation_quote_service_adapter_class(self) -> None:
        from apps.automation.services.insurance.preservation_quote_service_adapter import (
            PreservationQuoteServiceAdapter,
        )

        assert PreservationQuoteServiceAdapter is not None

    def test_quote_execution_mixin_class(self) -> None:
        from apps.automation.services.insurance._quote_execution_mixin import QuoteExecutionMixin

        assert QuoteExecutionMixin is not None

    def test_get_or_create_token_function(self) -> None:
        from apps.automation.services.insurance._quote_execution_mixin import get_or_create_token

        assert callable(get_or_create_token)


# ── document delivery services extended ──────────────────────────


class TestDocumentDeliveryExtended:
    def test_coordinator_class(self) -> None:
        from apps.automation.services.document_delivery.coordinator.document_delivery_coordinator import (
            DocumentDeliveryCoordinator,
        )

        assert DocumentDeliveryCoordinator is not None

    def test_court_sms_repo_class(self) -> None:
        from apps.automation.services.document_delivery.repo.court_sms_repo import CourtSmsRepo

        assert CourtSmsRepo is not None

    def test_document_history_repo_class(self) -> None:
        from apps.automation.services.document_delivery.repo.document_history_repo import (
            DocumentHistoryRepo,
        )

        assert DocumentHistoryRepo is not None

    def test_api_delivery_service_class(self) -> None:
        from apps.automation.services.document_delivery.delivery.api_delivery_service import (
            ApiDeliveryService,
        )

        assert ApiDeliveryService is not None

    def test_document_delivery_processor_class(self) -> None:
        from apps.automation.services.document_delivery.processor.document_delivery_processor import (
            DocumentDeliveryProcessor,
        )

        assert DocumentDeliveryProcessor is not None

    def test_court_document_api_client_class(self) -> None:
        from apps.automation.services.document_delivery.court_document_api_client import (
            CourtDocumentApiClient,
        )

        assert CourtDocumentApiClient is not None


# ── gsxt services extended ───────────────────────────────────────


class TestGsxtServicesExtended:
    def test_gsxt_login_service_class(self) -> None:
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginService

        assert GsxtLoginService is not None

    def test_gsxt_email_service_class(self) -> None:
        from apps.automation.services.gsxt.gsxt_email_service import GsxtEmailService

        assert GsxtEmailService is not None


# ── OCR services extended ────────────────────────────────────────


class TestOCRServicesExtended:
    def test_ocr_service_class(self) -> None:
        from apps.automation.services.ocr.ocr_service import OCRService

        assert OCRService is not None

    def test_paddleocr_api_service_class(self) -> None:
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        assert PaddleOCRApiEngine is not None


# ── document processing extended ─────────────────────────────────


class TestDocumentProcessingExtended:
    def test_document_extraction_class(self) -> None:
        from apps.automation.services.document.document_processing import DocumentExtraction

        assert DocumentExtraction is not None


# ── litigation services ──────────────────────────────────────────


# ── scraper services extended ─────────────────────────────────────


class TestScraperServicesExtended:
    def test_court_document_service_class(self) -> None:
        from apps.automation.services.scraper.court_document_service import CourtDocumentService

        assert CourtDocumentService is not None

    def test_validator_service_class(self) -> None:
        from apps.automation.services.scraper.core.validator_service import ValidatorService

        assert ValidatorService is not None

    def test_security_service_class(self) -> None:
        from apps.automation.services.scraper.core.security_service import SecurityService

        assert SecurityService is not None

    def test_token_service_class(self) -> None:
        from apps.automation.services.scraper.core.token_service import TokenService

        assert TokenService is not None

    def test_screenshot_utils_class(self) -> None:
        from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils

        assert ScreenshotUtils is not None


# ── token cache manager extended ─────────────────────────────────


class TestTokenCacheManagerExtended:
    @pytest.mark.django_db
    def test_cache_manager_class(self) -> None:
        from apps.automation.services.token.cache_manager import TokenCacheManager

        mgr = TokenCacheManager()
        assert mgr is not None


# ── performance monitor extended ─────────────────────────────────


class TestPerformanceMonitorExtended:
    @pytest.mark.django_db
    def test_performance_monitor_class(self) -> None:
        from apps.automation.services.token.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()
        assert monitor is not None

    def test_performance_metrics_class(self) -> None:
        from apps.automation.services.token.performance_monitor import PerformanceMetrics

        assert PerformanceMetrics is not None

    def test_alert_thresholds_class(self) -> None:
        from apps.automation.services.token.performance_monitor import AlertThresholds

        assert AlertThresholds is not None


# ── insurance preservation quote repo async ──────────────────────


class TestPreservationQuoteRepoAsync:
    @pytest.mark.django_db
    def test_get_quote_model_not_found(self) -> None:
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )
        from apps.core.exceptions import NotFoundError

        repo = PreservationQuoteRepository()
        with pytest.raises(NotFoundError):
            asyncio.run(repo.get_quote_model(quote_id=999999))

    @pytest.mark.django_db
    def test_get_quote_with_items_not_found(self) -> None:
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )
        from apps.core.exceptions import NotFoundError

        repo = PreservationQuoteRepository()
        with pytest.raises(NotFoundError):
            repo.get_quote_with_items(quote_id=999999)
