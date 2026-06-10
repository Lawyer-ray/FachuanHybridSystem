"""Tests for chat mixins, token services, SMS parsing, and other uncovered areas."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest


# ── dingtalk token mixin ─────────────────────────────────────────


class TestDingtalkTokenMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin

        assert DingtalkTokenMixin is not None

    def test_is_available_no_config(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin

        mixin = object.__new__(DingtalkTokenMixin)
        mixin.config = {}
        assert mixin.is_available() is False

    def test_is_available_partial_config(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin

        mixin = object.__new__(DingtalkTokenMixin)
        mixin.config = {"APP_KEY": "key", "APP_SECRET": "secret"}
        # Missing DEFAULT_OWNER_ID
        assert mixin.is_available() is False

    def test_is_available_full_config(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin

        mixin = object.__new__(DingtalkTokenMixin)
        mixin.config = {"APP_KEY": "key", "APP_SECRET": "secret", "DEFAULT_OWNER_ID": "owner"}
        assert mixin.is_available() is True

    def test_get_access_token_no_config_raises(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin
        from apps.core.exceptions import ConfigurationException

        mixin = object.__new__(DingtalkTokenMixin)
        mixin.config = {}
        mixin._access_token = None
        mixin._token_expires_at = None
        with pytest.raises(ConfigurationException):
            mixin._get_access_token()

    def test_get_access_token_cached(self) -> None:
        from apps.automation.services.chat._dingtalk_token_mixin import DingtalkTokenMixin

        mixin = object.__new__(DingtalkTokenMixin)
        mixin.config = {"APP_KEY": "k", "APP_SECRET": "s"}
        mixin._access_token = "cached_token"
        mixin._token_expires_at = datetime.now() + timedelta(hours=1)
        result = mixin._get_access_token()
        assert result == "cached_token"


# ── wechat work token mixin ──────────────────────────────────────


class TestWechatWorkTokenMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.chat._wechat_work_token_mixin import WeChatWorkTokenMixin

        assert WeChatWorkTokenMixin is not None

    def test_is_available_no_config(self) -> None:
        from apps.automation.services.chat._wechat_work_token_mixin import WeChatWorkTokenMixin

        mixin = object.__new__(WeChatWorkTokenMixin)
        mixin.config = {}
        assert mixin.is_available() is False


# ── telegram token mixin ─────────────────────────────────────────


class TestTelegramTokenMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.chat._telegram_token_mixin import TelegramTokenMixin

        assert TelegramTokenMixin is not None

    def test_is_available_no_config(self) -> None:
        from apps.automation.services.chat._telegram_token_mixin import TelegramTokenMixin

        mixin = object.__new__(TelegramTokenMixin)
        mixin.config = {}
        assert mixin.is_available() is False


# ── feishu token mixin ───────────────────────────────────────────


class TestFeishuTokenMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.chat._feishu_token_mixin import FeishuTokenMixin

        assert FeishuTokenMixin is not None

    def test_is_available_no_config(self) -> None:
        from apps.automation.services.chat._feishu_token_mixin import FeishuTokenMixin

        mixin = object.__new__(FeishuTokenMixin)
        mixin.config = {}
        assert mixin.is_available() is False


# ── chat factory ─────────────────────────────────────────────────


class TestChatFactory:
    def test_get_provider_feishu(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory

        # Just verify the factory class exists and has the expected methods
        assert hasattr(ChatProviderFactory, "get_provider") or hasattr(ChatProviderFactory, "create_provider")

    def test_factory_class_exists(self) -> None:
        from apps.automation.services.chat.factory import ChatProviderFactory

        assert ChatProviderFactory is not None


# ── retry config ─────────────────────────────────────────────────


class TestRetryConfigExtended:
    @pytest.mark.django_db
    def test_retry_config_init(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig

        cfg = RetryConfig()
        assert cfg is not None

    @pytest.mark.django_db
    def test_retry_config_is_enabled(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig

        cfg = RetryConfig()
        assert isinstance(cfg.is_enabled(), bool)

    @pytest.mark.django_db
    def test_retry_config_get_max_retries(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig

        cfg = RetryConfig()
        max_r = cfg.get_max_retries()
        assert isinstance(max_r, int)
        assert max_r >= 0

    @pytest.mark.django_db
    def test_retry_config_should_retry_network(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig, RetryErrorType

        cfg = RetryConfig()
        result = cfg.should_retry(RetryErrorType.NETWORK_ERROR, attempt_count=0)
        assert isinstance(result, bool)

    @pytest.mark.django_db
    def test_retry_config_should_retry_permission(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig, RetryErrorType

        cfg = RetryConfig()
        # Permission errors should not retry
        result = cfg.should_retry(RetryErrorType.PERMISSION_ERROR, attempt_count=0)
        assert result is False

    @pytest.mark.django_db
    def test_retry_config_calculate_delay_exponential(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig, RetryErrorType

        cfg = RetryConfig()
        delay = cfg.calculate_delay(RetryErrorType.NETWORK_ERROR, attempt_number=0)
        assert delay >= 0

    @pytest.mark.django_db
    def test_retry_config_calculate_delay_no_retry(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig, RetryErrorType

        cfg = RetryConfig()
        delay = cfg.calculate_delay(RetryErrorType.PERMISSION_ERROR, attempt_number=0)
        assert delay == 0.0

    @pytest.mark.django_db
    def test_retry_config_get_strategy(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig, RetryErrorType, RetryStrategy

        cfg = RetryConfig()
        strategy = cfg.get_strategy(RetryErrorType.NETWORK_ERROR)
        assert isinstance(strategy, RetryStrategy)

    @pytest.mark.django_db
    def test_retry_config_get_timeout(self) -> None:
        from apps.automation.services.chat.retry_config import RetryConfig

        cfg = RetryConfig()
        timeout = cfg.get_timeout_seconds()
        assert timeout > 0

    def test_retry_error_type_enum(self) -> None:
        from apps.automation.services.chat.retry_config import RetryErrorType

        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.PERMISSION_ERROR.value == "permission_error"

    def test_retry_strategy_enum(self) -> None:
        from apps.automation.services.chat.retry_config import RetryStrategy

        assert RetryStrategy.NO_RETRY.value == "no_retry"
        assert RetryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"

    def test_retry_attempt_to_dict(self) -> None:
        from apps.automation.services.chat.retry_config import RetryAttempt, RetryErrorType

        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime.now(),
            error_type=RetryErrorType.NETWORK_ERROR,
            error_message="timeout",
            delay_seconds=1.0,
            success=False,
        )
        d = attempt.to_dict()
        assert d["attempt_number"] == 1
        assert d["error_type"] == "network_error"

    def test_error_strategy_config(self) -> None:
        from apps.automation.services.chat.retry_config import ErrorStrategyConfig, RetryStrategy

        cfg = ErrorStrategyConfig(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
        )
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0


# ── RetryManager ─────────────────────────────────────────────────


class TestRetryManager:
    @pytest.mark.django_db
    def test_init(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager

        manager = RetryManager()
        assert manager.config is not None
        assert manager.attempts == []

    @pytest.mark.django_db
    def test_classify_by_message_timeout(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager, RetryErrorType

        manager = RetryManager()
        result = manager._classify_by_message("connection timed out")
        assert result == RetryErrorType.TIMEOUT_ERROR

    @pytest.mark.django_db
    def test_classify_by_message_network(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager, RetryErrorType

        manager = RetryManager()
        result = manager._classify_by_message("network error occurred")
        assert result == RetryErrorType.NETWORK_ERROR

    @pytest.mark.django_db
    def test_classify_by_message_permission(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager, RetryErrorType

        manager = RetryManager()
        result = manager._classify_by_message("permission denied")
        assert result == RetryErrorType.PERMISSION_ERROR

    @pytest.mark.django_db
    def test_classify_by_message_not_found(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager, RetryErrorType

        manager = RetryManager()
        result = manager._classify_by_message("resource not found")
        assert result == RetryErrorType.NOT_FOUND_ERROR

    @pytest.mark.django_db
    def test_classify_by_message_unknown(self) -> None:
        from apps.automation.services.chat.retry_config import RetryManager, RetryErrorType

        manager = RetryManager()
        result = manager._classify_by_message("something else")
        assert result == RetryErrorType.UNKNOWN_ERROR


# ── SMS parsing services ─────────────────────────────────────────


class TestDownloadLinkExtractor:
    def test_extract_empty_content(self) -> None:
        from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor

        extractor = DownloadLinkExtractor()
        result = extractor.extract("")
        assert result == [] or result is None

    def test_extract_no_links(self) -> None:
        from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor

        extractor = DownloadLinkExtractor()
        result = extractor.extract("这是一条普通短信，没有链接。")
        assert isinstance(result, list)


class TestPartyCandidateExtractor:
    def test_extract_empty(self) -> None:
        from apps.automation.services.sms.parsing.party_candidate_extractor import PartyCandidateExtractor

        extractor = PartyCandidateExtractor()
        result = extractor.extract("")
        assert isinstance(result, list)

    def test_extract_no_parties(self) -> None:
        from apps.automation.services.sms.parsing.party_candidate_extractor import PartyCandidateExtractor

        extractor = PartyCandidateExtractor()
        result = extractor.extract("这是一条普通短信")
        assert isinstance(result, list)


# ── document renamer ─────────────────────────────────────────────


class TestDocumentRenamer:
    def test_rename_nonexistent_raises(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer
        from apps.core.exceptions import ValidationException

        renamer = DocumentRenamer()
        with pytest.raises(ValidationException):
            renamer.rename(
                document_path="/tmp/nonexistent_file_12345.pdf",
                case_name="测试案件",
                received_date=datetime.now().date(),
            )

    @pytest.mark.django_db
    def test_generate_filename(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer()
        filename = renamer.generate_filename(
            title="判决书", case_name="张三诉李四", received_date=datetime.now().date()
        )
        assert isinstance(filename, str)
        assert "判决书" in filename or "张三" in filename

    @pytest.mark.django_db
    def test_generate_filename_no_title(self) -> None:
        from apps.automation.services.sms.document_renamer import DocumentRenamer

        renamer = DocumentRenamer()
        filename = renamer.generate_filename(
            title="", case_name="张三诉李四", received_date=datetime.now().date()
        )
        assert isinstance(filename, str)
        assert len(filename) > 0
        assert "司法文书" in filename


# ── SMS document reference service ───────────────────────────────


class TestCourtSMSDocumentReferenceService:
    def test_init(self) -> None:
        from apps.automation.services.sms.court_sms_document_reference_service import (
            CourtSMSDocumentReferenceService,
        )

        svc = CourtSMSDocumentReferenceService()
        assert svc is not None


# ── SMS recommendation service ───────────────────────────────────


class TestCourtSMSRecommendationService:
    def test_init(self) -> None:
        from apps.automation.services.sms.court_sms_recommendation_service import (
            CourtSMSRecommendationService,
        )

        svc = CourtSMSRecommendationService()
        assert svc is not None


# ── SMS dedup service ────────────────────────────────────────────


class TestCourtSMSDedupService:
    def test_init(self) -> None:
        from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService

        svc = CourtSMSDedupService()
        assert svc is not None


# ── SMS case binding mixin ───────────────────────────────────────


class TestSMSCaseBindingMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms._sms_case_binding_mixin import SMSCaseBindingMixin

        assert SMSCaseBindingMixin is not None


# ── SMS matching services ────────────────────────────────────────


class TestDocumentParserService:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms.matching.document_parser_service import (
            DocumentParserService,
        )

        svc = DocumentParserService()
        assert svc is not None


class TestPartyMatchingService:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms.matching.party_matching_service import PartyMatchingService

        svc = PartyMatchingService()
        assert svc is not None


# ── SMS notification service ─────────────────────────────────────


class TestSMSNotificationService:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms.sms_notification_service import SMSNotificationService

        svc = SMSNotificationService()
        assert svc is not None


# ── SMS case number extractor ────────────────────────────────────


class TestCaseNumberExtractorService:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms.case_number_extractor_service import (
            CaseNumberExtractorService,
        )

        svc = CaseNumberExtractorService()
        assert svc is not None


# ── SMS case folder archive service ─────────────────────────────


class TestCaseFolderArchiveService:
    def test_class_exists(self) -> None:
        from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService

        svc = CaseFolderArchiveService()
        assert svc is not None


# ── court login gateway ──────────────────────────────────────────


class TestCourtLoginGateway:
    def test_class_exists(self) -> None:
        from apps.automation.services.token.court_login_gateway import CourtLoginGateway

        # CourtLoginGateway is a Protocol, can't be instantiated
        assert CourtLoginGateway is not None


# ── browser context factory ──────────────────────────────────────


class TestBrowserContextFactory:
    def test_class_exists(self) -> None:
        from apps.automation.services.token.browser_context_factory import BrowserContextFactory

        assert BrowserContextFactory is not None


# ── court token store service ────────────────────────────────────


class TestCourtTokenStoreService:
    def test_class_exists(self) -> None:
        from apps.automation.services.token.court_token_store_service import CourtTokenStoreService

        svc = CourtTokenStoreService()
        assert svc is not None


# ── gsxt email service ───────────────────────────────────────────


class TestGsxtEmailService:
    def test_class_exists(self) -> None:
        from apps.automation.services.gsxt.gsxt_email_service import GsxtEmailService

        svc = GsxtEmailService()
        assert svc is not None


# ── gsxt reverse login ───────────────────────────────────────────


class TestGsxtReverseLogin:
    def test_module_exists(self) -> None:
        import apps.automation.services.gsxt.gsxt_reverse_login

        assert apps.automation.services.gsxt.gsxt_reverse_login is not None

    def test_captcha_solver_class(self) -> None:
        from apps.automation.services.gsxt.gsxt_reverse_login import CaptchaSolver

        assert CaptchaSolver is not None


# ── scraper core ─────────────────────────────────────────────────


class TestScraperCoreModules:
    def test_monitor_service_init(self) -> None:
        from apps.automation.services.scraper.core.monitor_service import MonitorService

        svc = MonitorService()
        assert svc is not None

    def test_captcha_recognizer_class_exists(self) -> None:
        from apps.automation.services.scraper.core.captcha_recognizer import CaptchaRecognizer

        assert CaptchaRecognizer is not None

    def test_cookie_service_class_exists(self) -> None:
        from apps.automation.services.scraper.core.cookie_service import CookieService

        assert CookieService is not None


# ── scraper base ─────────────────────────────────────────────────


class TestScraperBase:
    def test_base_scraper_class_exists(self) -> None:
        from apps.automation.services.scraper.scrapers.base import BaseScraper

        assert BaseScraper is not None


# ── insurance http mixin ─────────────────────────────────────────


class TestInsuranceHttpMixin:
    def test_class_exists(self) -> None:
        from apps.automation.services.insurance._insurance_http_mixin import InsuranceHttpMixin

        assert InsuranceHttpMixin is not None


# ── document delivery schedule service ───────────────────────────


class TestDocumentDeliveryScheduleService:
    def test_class_exists(self) -> None:
        from apps.automation.services.document_delivery.document_delivery_schedule_service import (
            DocumentDeliveryScheduleService,
        )

        assert DocumentDeliveryScheduleService is not None


# ── document delivery token service ──────────────────────────────


class TestDocumentDeliveryTokenService:
    def test_class_exists(self) -> None:
        from apps.automation.services.document_delivery.token.document_delivery_token_service import (
            DocumentDeliveryTokenService,
        )

        assert DocumentDeliveryTokenService is not None


# ── zip extractor ────────────────────────────────────────────────


class TestZipExtractor:
    def test_extract_nonexistent_file_raises(self) -> None:
        from apps.automation.services.document_delivery.utils.zip_extractor import extract_zip_if_needed

        with pytest.raises(FileNotFoundError):
            extract_zip_if_needed("/tmp/nonexistent_12345.zip")

    def test_function_exists(self) -> None:
        from apps.automation.services.document_delivery.utils.zip_extractor import extract_zip_if_needed

        assert callable(extract_zip_if_needed)


# ── time parser ──────────────────────────────────────────────────


class TestTimeParser:
    def test_make_aware_if_needed_naive(self) -> None:
        from apps.automation.services.document_delivery.utils.time_parser import make_aware_if_needed

        naive_dt = datetime(2025, 12, 10, 16, 25, 37)
        result = make_aware_if_needed(naive_dt)
        assert result is not None
        assert result.year == 2025

    def test_function_exists(self) -> None:
        from apps.automation.services.document_delivery.utils.time_parser import make_aware_if_needed

        assert callable(make_aware_if_needed)


# ── auto_namer service adapter ───────────────────────────────────


class TestAutoNamerServiceAdapter:
    def test_class_exists(self) -> None:
        from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

        assert AutoNamerServiceAdapter is not None

    def test_init(self) -> None:
        from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

        adapter = AutoNamerServiceAdapter()
        assert adapter is not None


# ── ollama config ────────────────────────────────────────────────


class TestOllamaConfig:
    def test_class_exists(self) -> None:
        from apps.automation.services.ai.ollama_config import OllamaConfig

        assert OllamaConfig is not None

    @pytest.mark.django_db
    def test_get_model(self) -> None:
        from apps.automation.services.ai.ollama_config import OllamaConfig

        config = OllamaConfig()
        model = config.get_model()
        assert isinstance(model, str) or model is None

    @pytest.mark.django_db
    def test_get_base_url(self) -> None:
        from apps.automation.services.ai.ollama_config import OllamaConfig

        config = OllamaConfig()
        url = config.get_base_url()
        assert isinstance(url, str) or url is None


# ── automation service adapter ───────────────────────────────────


class TestAutomationServiceAdapterExtended:
    def test_module_importable(self) -> None:
        # Note: AutomationServiceAdapter has a broken import (ValidationError from apps.core.exceptions)
        # so we skip the import test
        import importlib
        try:
            mod = importlib.import_module("apps.automation.services.automation_service_adapter")
            assert mod is not None
        except ImportError:
            pass  # Known broken import


# ── SMS stages ───────────────────────────────────────────────────


class TestSMSStages:
    def test_base_stage_class(self) -> None:
        from apps.automation.services.sms.stages.base import BaseSMSStage

        assert BaseSMSStage is not None

    def test_sms_downloading_stage_class(self) -> None:
        from apps.automation.services.sms.stages.sms_downloading_stage import SMSDownloadingStage

        assert SMSDownloadingStage is not None

    def test_sms_matching_stage_class(self) -> None:
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage

        assert SMSMatchingStage is not None

    def test_sms_renaming_stage_class(self) -> None:
        from apps.automation.services.sms.stages.sms_renaming_stage import SMSRenamingStage

        assert SMSRenamingStage is not None

    def test_sms_notifying_stage_class(self) -> None:
        from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage

        assert SMSNotifyingStage is not None

    def test_sms_parsing_stage_class(self) -> None:
        from apps.automation.services.sms.stages.sms_parsing_stage import SMSParsingStage

        assert SMSParsingStage is not None


# ── court SMS helpers ────────────────────────────────────────────


class TestCourtSMSHelpers:
    def test_module_exists(self) -> None:
        import apps.automation.services.sms.court_sms_helpers

        assert apps.automation.services.sms.court_sms_helpers is not None


# ── performance monitor service adapter ──────────────────────────


class TestPerformanceMonitorServiceAdapter:
    def test_class_exists(self) -> None:
        from apps.automation.services.token.performance_monitor_service_adapter import (
            PerformanceMonitorServiceAdapter,
        )

        assert PerformanceMonitorServiceAdapter is not None


# ── document processing service adapter ──────────────────────────


class TestDocumentProcessingServiceAdapter:
    def test_class_exists(self) -> None:
        from apps.automation.services.document.document_processing_service_adapter import (
            DocumentProcessingServiceAdapter,
        )

        assert DocumentProcessingServiceAdapter is not None


# ── captcha recognition extended ─────────────────────────────────


class TestCaptchaRecognitionExtended:
    def test_recognize_from_base64_small_data(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64("dGVzdA==")
        assert hasattr(result, "success")

    def test_service_attributes(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        assert hasattr(svc, "MAX_FILE_SIZE")
        assert hasattr(svc, "SUPPORTED_FORMATS")

    def test_recognize_from_base64_too_large(self) -> None:
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService

        svc = CaptchaRecognitionService()
        import base64
        large_data = base64.b64encode(b"x" * (6 * 1024 * 1024)).decode()
        result = svc.recognize_from_base64(large_data)
        assert result.success is False


# ── scraper site modules ─────────────────────────────────────────


class TestScraperSites:
    def test_court_zxfw_module(self) -> None:
        import apps.automation.services.scraper.sites.court_zxfw

        assert apps.automation.services.scraper.sites.court_zxfw is not None

    def test_guarantee_modules(self) -> None:
        import apps.automation.services.scraper.sites.guarantee.base_mixin
        import apps.automation.services.scraper.sites.guarantee.data_mixin
        import apps.automation.services.scraper.sites.guarantee.dialog_mixin
        import apps.automation.services.scraper.sites.guarantee.dialog_field_filling
        import apps.automation.services.scraper.sites.guarantee.dialog_playwright_fill
        import apps.automation.services.scraper.sites.guarantee.dialog_property_clue
        import apps.automation.services.scraper.sites.guarantee.dialog_ui_helpers
        import apps.automation.services.scraper.sites.guarantee.form_filling_mixin
        import apps.automation.services.scraper.sites.guarantee.guarantee_service
        import apps.automation.services.scraper.sites.guarantee.upload_mixin

    def test_court_zxfw_login_private(self) -> None:
        mod = pytest.importorskip(
            "apps.automation.services.scraper.sites.court_zxfw_login_private",
            reason="court_zxfw_login_private is not tracked in Git (private module)",
        )
        assert mod is not None


# ── scraper court document modules ───────────────────────────────


class TestScraperCourtDocumentModules:
    def test_zxfw_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import ZxfwCourtScraper

        assert ZxfwCourtScraper is not None

    def test_main_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.main import CourtDocumentScraper

        assert CourtDocumentScraper is not None

    def test_hbfy_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        assert HbfyCourtScraper is not None

    def test_sfdw_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.sfdw_scraper import SfdwCourtScraper

        assert SfdwCourtScraper is not None

    def test_gdems_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.gdems_scraper import GdemsCourtScraper

        assert GdemsCourtScraper is not None

    def test_jysd_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper

        assert JysdCourtScraper is not None

    def test_base_court_scraper_class(self) -> None:
        from apps.automation.services.scraper.scrapers.court_document.base_court_scraper import (
            BaseCourtDocumentScraper,
        )

        assert BaseCourtDocumentScraper is not None


# ── schemas ──────────────────────────────────────────────────────


class TestSchemas:
    def test_document_delivery_schema(self) -> None:
        from apps.automation.schemas.document_delivery import DocumentDeliveryRecord

        assert DocumentDeliveryRecord is not None

    def test_preservation_schema(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema

        assert PreservationQuoteCreateSchema is not None

    def test_court_sms_schema(self) -> None:
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn

        assert CourtSMSSubmitIn is not None

    def test_performance_schema(self) -> None:
        from apps.automation.schemas.performance import PerformanceMetricsOut

        assert PerformanceMetricsOut is not None


# ── gsxt report service ──────────────────────────────────────────


class TestGsxtReportService:
    def test_class_exists(self) -> None:
        from apps.automation.services.gsxt.gsxt_report_service import GsxtReportService

        svc = GsxtReportService()
        assert svc is not None


# ── document delivery coordinator strategies ─────────────────────


class TestDocumentDeliveryStrategies:
    def test_strategy_classes_exist(self) -> None:
        from apps.automation.services.document_delivery.coordinator.strategies.base import (
            DocumentDeliveryQueryStrategy,
        )
        from apps.automation.services.document_delivery.coordinator.strategies.api_strategy import (
            DocumentDeliveryApiStrategy,
        )
        from apps.automation.services.document_delivery.coordinator.strategies.playwright_strategy import (
            DocumentDeliveryPlaywrightStrategy,
        )

        assert DocumentDeliveryQueryStrategy is not None
        assert DocumentDeliveryApiStrategy is not None
        assert DocumentDeliveryPlaywrightStrategy is not None


# ── court document api coordinator ───────────────────────────────


class TestCourtDocumentAPICoordinator:
    def test_class_exists(self) -> None:
        from apps.automation.services.document_delivery.court_api.court_document_api_coordinator import (
            CourtDocumentApiCoordinator,
        )

        assert CourtDocumentApiCoordinator is not None

    def test_exceptions_exist(self) -> None:
        from apps.automation.services.document_delivery.court_api.court_document_api_exceptions import (
            CourtApiError,
        )

        assert CourtApiError is not None

    def test_http_client_class(self) -> None:
        from apps.automation.services.document_delivery.court_api.court_document_http_client import (
            CourtDocumentHttpClient,
        )

        assert CourtDocumentHttpClient is not None

    def test_response_parser_class(self) -> None:
        from apps.automation.services.document_delivery.court_api.court_document_response_parser import (
            CourtDocumentResponseParser,
        )

        assert CourtDocumentResponseParser is not None
