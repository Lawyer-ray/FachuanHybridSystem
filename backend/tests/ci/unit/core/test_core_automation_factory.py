"""core/exceptions/automation_factory.py 单元测试。"""

from __future__ import annotations

import pytest

from apps.core.exceptions.automation_factory import AutomationExceptions
from apps.core.exceptions.base import BusinessException
from apps.core.exceptions.common import NotFoundError, ValidationException


class TestCaptchaExceptions:
    """验证码相关异常测试。"""

    def test_captcha_recognition_failed_basic(self) -> None:
        exc = AutomationExceptions.captcha_recognition_failed()
        assert "验证码识别失败" in exc.message
        assert exc.code == "CAPTCHA_RECOGNITION_FAILED"

    def test_captcha_recognition_failed_with_details(self) -> None:
        exc = AutomationExceptions.captcha_recognition_failed(details="OCR error", processing_time=2.5)
        assert exc.errors["details"] == "OCR error"
        assert exc.errors["processing_time"] == 2.5

    def test_captcha_recognition_error(self) -> None:
        exc = AutomationExceptions.captcha_recognition_error("timeout error")
        assert "验证码识别异常" in exc.message
        assert exc.errors["error_message"] == "timeout error"

    def test_captcha_recognition_error_with_original(self) -> None:
        original = ValueError("bad value")
        exc = AutomationExceptions.captcha_recognition_error("msg", original)
        assert "bad value" in exc.errors["original_error"]


class TestTokenExceptions:
    """Token 相关异常测试。"""

    def test_token_acquisition_failed(self) -> None:
        exc = AutomationExceptions.token_acquisition_failed("network error", site_name="test_site")
        assert "Token获取失败" in exc.message
        assert exc.errors["reason"] == "network error"
        assert exc.errors["site_name"] == "test_site"

    def test_token_acquisition_failed_with_account(self) -> None:
        exc = AutomationExceptions.token_acquisition_failed("err", account="user1")
        assert exc.errors["account"] == "user1"

    def test_no_available_account_error(self) -> None:
        exc = AutomationExceptions.no_available_account_error("某网站")
        assert "某网站" in exc.message
        assert exc.code == "NO_AVAILABLE_ACCOUNT"

    def test_invalid_credential_error(self) -> None:
        exc = AutomationExceptions.invalid_credential_error(42)
        assert "42" in exc.message
        assert exc.code == "INVALID_CREDENTIAL_ID"

    def test_login_timeout_error(self) -> None:
        exc = AutomationExceptions.login_timeout_error(30, site_name="test")
        assert "30" in exc.message
        assert exc.code == "LOGIN_TIMEOUT"


class TestDocumentExceptions:
    """文档相关异常测试。"""

    def test_document_not_found(self) -> None:
        exc = AutomationExceptions.document_not_found(123)
        assert "文档不存在" in exc.message
        assert exc.errors["document_id"] == 123
        assert isinstance(exc, NotFoundError)

    def test_missing_required_fields(self) -> None:
        exc = AutomationExceptions.missing_required_fields(["name", "type"])
        assert "name" in exc.message
        assert "type" in exc.message
        assert exc.errors["missing_fields"] == ["name", "type"]

    def test_invalid_download_status(self) -> None:
        exc = AutomationExceptions.invalid_download_status("bad", ["ok", "done"])
        assert "bad" in exc.message
        assert exc.errors["valid_statuses"] == ["ok", "done"]

    def test_create_document_failed(self) -> None:
        exc = AutomationExceptions.create_document_failed("API error", {"key": "val"})
        assert "API error" in exc.message
        assert exc.errors["api_data_keys"] == ["key"]

    def test_create_document_failed_no_api_data(self) -> None:
        exc = AutomationExceptions.create_document_failed("err")
        assert "api_data_keys" not in exc.errors


class TestProcessingExceptions:
    """文档处理相关异常测试。"""

    def test_pdf_processing_failed(self) -> None:
        exc = AutomationExceptions.pdf_processing_failed("corrupt file")
        assert "corrupt file" in exc.message
        assert exc.code == "PDF_PROCESSING_FAILED"

    def test_docx_processing_failed(self) -> None:
        exc = AutomationExceptions.docx_processing_failed("bad format")
        assert "bad format" in exc.message

    def test_image_ocr_failed(self) -> None:
        exc = AutomationExceptions.image_ocr_failed("blurry image")
        assert "blurry image" in exc.message

    def test_document_content_extraction_failed(self) -> None:
        exc = AutomationExceptions.document_content_extraction_failed("no text")
        assert "no text" in exc.message

    def test_empty_document_content(self) -> None:
        exc = AutomationExceptions.empty_document_content()
        assert "文档内容不能为空" in exc.message


class TestAIExceptions:
    """AI 相关异常测试。"""

    def test_ai_filename_generation_failed(self) -> None:
        exc = AutomationExceptions.ai_filename_generation_failed("model error")
        assert "model error" in exc.message
        assert exc.code == "AI_FILENAME_GENERATION_FAILED"

    def test_document_naming_processing_failed(self) -> None:
        exc = AutomationExceptions.document_naming_processing_failed("naming error")
        assert "naming error" in exc.message


class TestAudioExceptions:
    """语音相关异常测试。"""

    def test_unsupported_audio_format(self) -> None:
        exc = AutomationExceptions.unsupported_audio_format(".wav", [".mp3", ".m4a"])
        assert ".wav" in exc.message
        assert exc.errors["supported_formats"] == [".mp3", ".m4a"]

    def test_audio_transcription_failed(self) -> None:
        exc = AutomationExceptions.audio_transcription_failed("no speech")
        assert "no speech" in exc.message

    def test_missing_file_name(self) -> None:
        exc = AutomationExceptions.missing_file_name()
        assert "文件名" in exc.message


class TestPerformanceExceptions:
    """性能监控相关异常测试。"""

    def test_system_metrics_failed(self) -> None:
        exc = AutomationExceptions.system_metrics_failed("timeout")
        assert "timeout" in exc.message

    def test_token_acquisition_metrics_failed(self) -> None:
        exc = AutomationExceptions.token_acquisition_metrics_failed("err")
        assert exc.code == "TOKEN_ACQUISITION_METRICS_FAILED"

    def test_api_performance_metrics_failed(self) -> None:
        exc = AutomationExceptions.api_performance_metrics_failed("err")
        assert exc.code == "API_PERFORMANCE_METRICS_FAILED"


class TestAdminExceptions:
    """Admin 相关异常测试。"""

    def test_invalid_days_parameter(self) -> None:
        exc = AutomationExceptions.invalid_days_parameter()
        assert "保留天数" in exc.message

    def test_no_records_selected(self) -> None:
        exc = AutomationExceptions.no_records_selected()
        assert "没有选中" in exc.message

    def test_cleanup_records_failed(self) -> None:
        exc = AutomationExceptions.cleanup_records_failed()
        assert exc.code == "CLEANUP_RECORDS_FAILED"

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
    """询价相关异常测试。"""

    def test_no_quotes_selected(self) -> None:
        exc = AutomationExceptions.no_quotes_selected()
        assert "询价" in exc.message

    def test_no_executable_quotes(self) -> None:
        exc = AutomationExceptions.no_executable_quotes()
        assert "可执行" in exc.message

    def test_execute_quotes_failed(self) -> None:
        exc = AutomationExceptions.execute_quotes_failed()
        assert exc.code == "EXECUTE_QUOTES_FAILED"

    def test_retry_failed_quotes_failed(self) -> None:
        exc = AutomationExceptions.retry_failed_quotes_failed()
        assert exc.code == "RETRY_FAILED_QUOTES_FAILED"

    def test_get_quote_stats_failed(self) -> None:
        exc = AutomationExceptions.get_quote_stats_failed()
        assert exc.code == "GET_QUOTE_STATS_FAILED"

    def test_no_quote_configs(self) -> None:
        exc = AutomationExceptions.no_quote_configs()
        assert "询价配置" in exc.message

    def test_missing_preserve_amount(self) -> None:
        exc = AutomationExceptions.missing_preserve_amount()
        assert "保全金额" in exc.message


class TestGenericParamExceptions:
    """通用参数验证异常测试。"""

    def test_empty_site_name(self) -> None:
        exc = AutomationExceptions.empty_site_name()
        assert "网站名称" in exc.message

    def test_empty_account_list(self) -> None:
        exc = AutomationExceptions.empty_account_list()
        assert "没有可用账号" in exc.message


class TestRecognitionExceptionExceptions:
    """文书识别相关异常测试。"""

    def test_unsupported_file_format_default(self) -> None:
        exc = AutomationExceptions.unsupported_file_format(".doc")
        assert ".doc" in exc.errors["file"]
        assert ".pdf" in exc.errors["supported_formats"]

    def test_unsupported_file_format_custom(self) -> None:
        exc = AutomationExceptions.unsupported_file_format(".tiff", [".pdf", ".jpg"])
        assert exc.errors["supported_formats"] == [".pdf", ".jpg"]

    def test_file_not_found(self) -> None:
        exc = AutomationExceptions.file_not_found("/path/to/file")
        assert "/path/to/file" in exc.errors["file"]

    def test_text_extraction_failed(self) -> None:
        exc = AutomationExceptions.text_extraction_failed("error msg", "/path")
        assert exc.errors["file_path"] == "/path"

    def test_text_extraction_failed_no_path(self) -> None:
        exc = AutomationExceptions.text_extraction_failed("error")
        assert "file_path" not in exc.errors

    def test_ai_service_unavailable(self) -> None:
        exc = AutomationExceptions.ai_service_unavailable("ChatGPT", "rate limited")
        assert "ChatGPT" in exc.errors["service"]
        assert exc.errors["error_message"] == "rate limited"

    def test_recognition_timeout(self) -> None:
        exc = AutomationExceptions.recognition_timeout(30.0, "OCR")
        assert exc.timeout_seconds == 30.0
        assert exc.errors["operation"] == "OCR"

    def test_recognition_timeout_no_operation(self) -> None:
        exc = AutomationExceptions.recognition_timeout(10.0)
        assert "operation" not in exc.errors

    def test_document_classification_failed(self) -> None:
        exc = AutomationExceptions.document_classification_failed("model error")
        assert exc.code == "DOCUMENT_CLASSIFICATION_FAILED"

    def test_info_extraction_failed_with_type(self) -> None:
        exc = AutomationExceptions.info_extraction_failed("err", "合同")
        assert exc.errors["document_type"] == "合同"

    def test_info_extraction_failed_without_type(self) -> None:
        exc = AutomationExceptions.info_extraction_failed("err")
        assert "document_type" not in exc.errors

    def test_case_binding_failed(self) -> None:
        exc = AutomationExceptions.case_binding_failed("(2026)粤01民初1号", "not found")
        assert "(2026)粤01民初1号" in exc.errors["case_number"]

    def test_case_not_found_for_binding(self) -> None:
        exc = AutomationExceptions.case_not_found_for_binding("案号123")
        assert "案号123" in exc.message
        assert isinstance(exc, NotFoundError)
