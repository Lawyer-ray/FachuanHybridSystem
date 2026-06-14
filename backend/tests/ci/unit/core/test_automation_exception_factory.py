"""Tests for core.exceptions.automation_factory: AutomationExceptions factory methods."""
from __future__ import annotations

from apps.core.exceptions import (
    BusinessException,
    NotFoundError,
    ValidationException,
)
from apps.core.exceptions.automation_factory import AutomationExceptions
from apps.core.exceptions.external import RecognitionTimeoutError, ServiceUnavailableError


class TestCaptchaExceptions:
    def test_captcha_recognition_failed_minimal(self) -> None:
        exc = AutomationExceptions.captcha_recognition_failed()
        assert isinstance(exc, ValidationException)
        assert exc.code == "CAPTCHA_RECOGNITION_FAILED"

    def test_captcha_recognition_failed_with_details(self) -> None:
        exc = AutomationExceptions.captcha_recognition_failed(
            details="bad image", processing_time=1.5
        )
        assert exc.errors["details"] == "bad image"
        assert exc.errors["processing_time"] == 1.5

    def test_captcha_recognition_error(self) -> None:
        exc = AutomationExceptions.captcha_recognition_error("runtime error")
        assert exc.code == "CAPTCHA_RECOGNITION_ERROR"
        assert exc.errors["error_message"] == "runtime error"

    def test_captcha_recognition_error_with_original(self) -> None:
        orig = ValueError("boom")
        exc = AutomationExceptions.captcha_recognition_error("fail", original_exception=orig)
        assert "boom" in str(exc.errors["original_error"])


class TestTokenExceptions:
    def test_token_acquisition_failed(self) -> None:
        exc = AutomationExceptions.token_acquisition_failed("expired")
        assert isinstance(exc, BusinessException)
        assert exc.code == "TOKEN_ACQUISITION_FAILED"
        assert exc.errors["reason"] == "expired"

    def test_token_with_optional_fields(self) -> None:
        exc = AutomationExceptions.token_acquisition_failed(
            "error", site_name="court", account="user1"
        )
        assert exc.errors["site_name"] == "court"
        assert exc.errors["account"] == "user1"

    def test_no_available_account(self) -> None:
        exc = AutomationExceptions.no_available_account_error("gsxt")
        assert exc.code == "NO_AVAILABLE_ACCOUNT"
        assert "gsxt" in exc.message

    def test_invalid_credential(self) -> None:
        exc = AutomationExceptions.invalid_credential_error(42)
        assert exc.errors["credential_id"] == 42

    def test_login_timeout(self) -> None:
        exc = AutomationExceptions.login_timeout_error(30)
        assert exc.code == "LOGIN_TIMEOUT"
        assert "30" in exc.message

    def test_login_timeout_with_optional(self) -> None:
        exc = AutomationExceptions.login_timeout_error(60, site_name="court", account="admin")
        assert exc.errors["site_name"] == "court"
        assert exc.errors["account"] == "admin"


class TestDocumentExceptions:
    def test_document_not_found(self) -> None:
        exc = AutomationExceptions.document_not_found(10)
        assert isinstance(exc, NotFoundError)
        assert exc.errors["document_id"] == 10

    def test_missing_required_fields(self) -> None:
        exc = AutomationExceptions.missing_required_fields(["name", "email"])
        assert "name" in exc.message
        assert exc.errors["missing_fields"] == ["name", "email"]

    def test_invalid_download_status(self) -> None:
        exc = AutomationExceptions.invalid_download_status("bad", ["ok", "pending"])
        assert exc.errors["invalid_status"] == "bad"
        assert exc.errors["valid_statuses"] == ["ok", "pending"]

    def test_create_document_failed(self) -> None:
        exc = AutomationExceptions.create_document_failed("timeout")
        assert "timeout" in exc.message

    def test_create_document_failed_with_api_data(self) -> None:
        exc = AutomationExceptions.create_document_failed("error", api_data={"key": "val"})
        assert exc.errors["api_data_keys"] == ["key"]


class TestDocumentProcessingExceptions:
    def test_pdf_processing_failed(self) -> None:
        exc = AutomationExceptions.pdf_processing_failed("corrupt")
        assert exc.code == "PDF_PROCESSING_FAILED"

    def test_docx_processing_failed(self) -> None:
        exc = AutomationExceptions.docx_processing_failed("bad template")
        assert exc.code == "DOCX_PROCESSING_FAILED"

    def test_image_ocr_failed(self) -> None:
        exc = AutomationExceptions.image_ocr_failed("low quality")
        assert exc.code == "IMAGE_OCR_FAILED"

    def test_document_content_extraction_failed(self) -> None:
        exc = AutomationExceptions.document_content_extraction_failed("no text found")
        assert exc.code == "DOCUMENT_CONTENT_EXTRACTION_FAILED"

    def test_empty_document_content(self) -> None:
        exc = AutomationExceptions.empty_document_content()
        assert exc.code == "EMPTY_DOCUMENT_CONTENT"


class TestAIExceptions:
    def test_ai_filename_generation_failed(self) -> None:
        exc = AutomationExceptions.ai_filename_generation_failed("model down")
        assert isinstance(exc, BusinessException)

    def test_document_naming_processing_failed(self) -> None:
        exc = AutomationExceptions.document_naming_processing_failed("timeout")
        assert exc.code == "DOCUMENT_NAMING_PROCESSING_FAILED"


class TestAudioExceptions:
    def test_unsupported_audio_format(self) -> None:
        exc = AutomationExceptions.unsupported_audio_format(".wma", [".mp3", ".wav"])
        assert exc.errors["file_extension"] == ".wma"
        assert ".mp3" in exc.errors["supported_formats"]

    def test_audio_transcription_failed(self) -> None:
        exc = AutomationExceptions.audio_transcription_failed("network error")
        assert exc.code == "AUDIO_TRANSCRIPTION_FAILED"

    def test_missing_file_name(self) -> None:
        exc = AutomationExceptions.missing_file_name()
        assert exc.code == "MISSING_FILE_NAME"


class TestPerformanceExceptions:
    def test_system_metrics_failed(self) -> None:
        exc = AutomationExceptions.system_metrics_failed("CPU error")
        assert exc.code == "SYSTEM_METRICS_FAILED"

    def test_token_acquisition_metrics_failed(self) -> None:
        exc = AutomationExceptions.token_acquisition_metrics_failed("err")
        assert exc.code == "TOKEN_ACQUISITION_METRICS_FAILED"

    def test_api_performance_metrics_failed(self) -> None:
        exc = AutomationExceptions.api_performance_metrics_failed("timeout")
        assert exc.code == "API_PERFORMANCE_METRICS_FAILED"


class TestAdminExceptions:
    def test_invalid_days_parameter(self) -> None:
        exc = AutomationExceptions.invalid_days_parameter()
        assert exc.code == "INVALID_DAYS_PARAMETER"

    def test_no_records_selected(self) -> None:
        exc = AutomationExceptions.no_records_selected()
        assert exc.code == "NO_RECORDS_SELECTED"

    def test_cleanup_records_failed(self) -> None:
        exc = AutomationExceptions.cleanup_records_failed()
        assert isinstance(exc, BusinessException)

    def test_export_csv_failed(self) -> None:
        exc = AutomationExceptions.export_csv_failed()
        assert exc.code == "EXPORT_CSV_FAILED"

    def test_performance_analysis_failed(self) -> None:
        exc = AutomationExceptions.performance_analysis_failed()
        assert exc.code == "PERFORMANCE_ANALYSIS_FAILED"

    def test_get_dashboard_stats_failed(self) -> None:
        exc = AutomationExceptions.get_dashboard_stats_failed()
        assert exc.code == "GET_DASHBOARD_STATS_FAILED"


class TestQuoteExceptions:
    def test_no_quotes_selected(self) -> None:
        exc = AutomationExceptions.no_quotes_selected()
        assert exc.code == "NO_QUOTES_SELECTED"

    def test_no_executable_quotes(self) -> None:
        exc = AutomationExceptions.no_executable_quotes()
        assert exc.code == "NO_EXECUTABLE_QUOTES"

    def test_execute_quotes_failed(self) -> None:
        exc = AutomationExceptions.execute_quotes_failed()
        assert isinstance(exc, BusinessException)

    def test_retry_failed_quotes_failed(self) -> None:
        exc = AutomationExceptions.retry_failed_quotes_failed()
        assert exc.code == "RETRY_FAILED_QUOTES_FAILED"

    def test_get_quote_stats_failed(self) -> None:
        exc = AutomationExceptions.get_quote_stats_failed()
        assert exc.code == "GET_QUOTE_STATS_FAILED"

    def test_no_quote_configs(self) -> None:
        exc = AutomationExceptions.no_quote_configs()
        assert exc.code == "NO_QUOTE_CONFIGS"

    def test_missing_preserve_amount(self) -> None:
        exc = AutomationExceptions.missing_preserve_amount()
        assert exc.code == "MISSING_PRESERVE_AMOUNT"


class TestGenericParamExceptions:
    def test_empty_site_name(self) -> None:
        exc = AutomationExceptions.empty_site_name()
        assert exc.code == "EMPTY_SITE_NAME"

    def test_empty_account_list(self) -> None:
        exc = AutomationExceptions.empty_account_list()
        assert exc.code == "EMPTY_ACCOUNT_LIST"


class TestRecognitionExceptions:
    def test_unsupported_file_format_default(self) -> None:
        exc = AutomationExceptions.unsupported_file_format(".docx")
        assert exc.code == "UNSUPPORTED_FILE_FORMAT"
        assert ".pdf" in exc.errors["supported_formats"]

    def test_unsupported_file_format_custom(self) -> None:
        exc = AutomationExceptions.unsupported_file_format(".bmp", [".tiff", ".png"])
        assert ".tiff" in exc.errors["supported_formats"]

    def test_file_not_found(self) -> None:
        exc = AutomationExceptions.file_not_found("/tmp/test.pdf")
        assert exc.code == "FILE_NOT_FOUND"

    def test_text_extraction_failed(self) -> None:
        exc = AutomationExceptions.text_extraction_failed("error msg")
        assert exc.errors["error_message"] == "error msg"

    def test_text_extraction_failed_with_path(self) -> None:
        exc = AutomationExceptions.text_extraction_failed("err", file_path="/tmp/f.pdf")
        assert exc.errors["file_path"] == "/tmp/f.pdf"

    def test_ai_service_unavailable_default(self) -> None:
        exc = AutomationExceptions.ai_service_unavailable()
        assert isinstance(exc, ServiceUnavailableError)
        assert exc.code == "AI_SERVICE_UNAVAILABLE"

    def test_ai_service_unavailable_custom(self) -> None:
        exc = AutomationExceptions.ai_service_unavailable("OpenAI", "rate limited")
        assert exc.errors["service"].startswith("OpenAI")
        assert exc.errors["error_message"] == "rate limited"

    def test_recognition_timeout(self) -> None:
        exc = AutomationExceptions.recognition_timeout(30.0)
        assert isinstance(exc, RecognitionTimeoutError)
        assert exc.errors["timeout"].startswith("识别超时")

    def test_recognition_timeout_with_operation(self) -> None:
        exc = AutomationExceptions.recognition_timeout(15.0, operation="OCR")
        assert exc.errors["operation"] == "OCR"

    def test_document_classification_failed(self) -> None:
        exc = AutomationExceptions.document_classification_failed("bad input")
        assert exc.code == "DOCUMENT_CLASSIFICATION_FAILED"

    def test_info_extraction_failed(self) -> None:
        exc = AutomationExceptions.info_extraction_failed("parse error")
        assert exc.code == "INFO_EXTRACTION_FAILED"

    def test_info_extraction_failed_with_type(self) -> None:
        exc = AutomationExceptions.info_extraction_failed("err", document_type="summons")
        assert exc.errors["document_type"] == "summons"

    def test_case_binding_failed(self) -> None:
        exc = AutomationExceptions.case_binding_failed("2024京01号", "no case found")
        assert exc.errors["case_number"] == "2024京01号"

    def test_case_not_found_for_binding(self) -> None:
        exc = AutomationExceptions.case_not_found_for_binding("2024京02号")
        assert isinstance(exc, NotFoundError)
        assert "2024京02号" in exc.message
