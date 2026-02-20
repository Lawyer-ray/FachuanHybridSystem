"""Custom exceptions."""

from typing import Any

from apps.core.exceptions import (
    BusinessException,
    ExternalServiceError,
    NotFoundError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    ValidationException,
)


class AutoTokenAcquisitionError(ExternalServiceError):
    def __init__(
        self, message: str = "自动Token获取失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "AUTO_TOKEN_ACQUISITION_ERROR", errors=errors)


class LoginFailedError(AutoTokenAcquisitionError):
    def __init__(
        self,
        message: str = "登录失败",
        code: str | None = None,
        errors: dict[str, Any] | None = None,
        attempts: list[Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code or "LOGIN_FAILED", errors=errors)
        self.attempts = attempts or []


class NoAvailableAccountError(AutoTokenAcquisitionError):
    def __init__(
        self, message: str = "无可用账号", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "NO_AVAILABLE_ACCOUNT", errors=errors)


class TokenAcquisitionTimeoutError(AutoTokenAcquisitionError):
    def __init__(
        self, message: str = "Token获取超时", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "TOKEN_ACQUISITION_TIMEOUT", errors=errors)


class CaptchaRecognitionError(ExternalServiceError):
    def __init__(
        self, message: str = "验证码识别失败", code: str | None = None, errors: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message=message, code=code or "CAPTCHA_RECOGNITION_ERROR", errors=errors)


class AutomationExceptions:
    @staticmethod
    def captcha_recognition_failed(
        details: str | None = None, processing_time: float | None = None
    ) -> ValidationException:
        errors: dict[str, Any] = {}
        if details:
            errors["details"] = details
        if processing_time is not None:
            errors["processing_time"] = processing_time
        return ValidationException(message="验证码识别失败", code="CAPTCHA_RECOGNITION_FAILED", errors=errors)

    @staticmethod
    def captcha_recognition_error(
        error_message: str,
        original_exception: Exception | None = None,
    ) -> ValidationException:
        errors: dict[str, Any] = {"error_message": error_message}
        if original_exception:
            errors["original_error"] = str(original_exception)
        return ValidationException(message="验证码识别异常", code="CAPTCHA_RECOGNITION_ERROR", errors=errors)

    @staticmethod
    def token_acquisition_failed(
        reason: str, site_name: str | None = None, account: str | None = None
    ) -> BusinessException:
        errors = {"reason": reason}
        if site_name:
            errors["site_name"] = site_name
        if account:
            errors["account"] = account
        return BusinessException(message="Token获取失败", code="TOKEN_ACQUISITION_FAILED", errors=errors)

    @staticmethod
    def no_available_account_error(site_name: str) -> ValidationException:
        return ValidationException(
            message=f"网站 {site_name} 没有可用账号", code="NO_AVAILABLE_ACCOUNT", errors={"site_name": site_name}
        )

    @staticmethod
    def invalid_credential_error(credential_id: int) -> ValidationException:
        return ValidationException(
            message=f"指定的凭证ID不存在: {credential_id}", code="INVALID_CREDENTIAL_ID", errors={}
        )

    @staticmethod
    def login_timeout_error(
        timeout_seconds: int, site_name: str | None = None, account: str | None = None
    ) -> BusinessException:
        errors = {"timeout_seconds": timeout_seconds}
        if site_name:
            errors["site_name"] = site_name  # type: ignore[assignment]
        if account:
            errors["account"] = account  # type: ignore[assignment]
        return BusinessException(message=f"登录超时({timeout_seconds}秒)", code="LOGIN_TIMEOUT", errors=errors)

    @staticmethod
    def document_not_found(document_id: int) -> NotFoundError:
        return NotFoundError(message="文档不存在", code="DOCUMENT_NOT_FOUND", errors={"document_id": document_id})

    @staticmethod
    def missing_required_fields(missing_fields: list[Any]) -> ValidationException:
        return ValidationException(
            message=f"缺少必需字段: {', '.join(missing_fields)}",
            code="MISSING_REQUIRED_FIELDS",
            errors={"missing_fields": missing_fields},
        )

    @staticmethod
    def invalid_download_status(status: str, valid_statuses: list[Any]) -> ValidationException:
        return ValidationException(message=f"无效的下载状态: {status}", code="INVALID_DOWNLOAD_STATUS", errors={})

    @staticmethod
    def create_document_failed(error_message: str, api_data: dict[str, Any] | None = None) -> BusinessException:
        errors = {"error_message": error_message}
        if api_data:
            errors["api_data_keys"] = list(api_data.keys())  # type: ignore[assignment]
        return BusinessException(
            message=f"创建文书记录失败: {error_message}", code="CREATE_DOCUMENT_FAILED", errors=errors
        )

    @staticmethod
    def pdf_processing_failed(error_message: str) -> ValidationException:
        return ValidationException(message=f"PDF文件处理失败: {error_message}", code="PDF_PROCESSING_FAILED", errors={})

    @staticmethod
    def docx_processing_failed(error_message: str) -> ValidationException:
        return ValidationException(
            message=f"DOCX文件处理失败: {error_message}", code="DOCX_PROCESSING_FAILED", errors={}
        )

    @staticmethod
    def image_ocr_failed(error_message: str) -> ValidationException:
        return ValidationException(message=f"图片OCR处理失败: {error_message}", code="IMAGE_OCR_FAILED", errors={})

    @staticmethod
    def document_content_extraction_failed(error_message: str) -> ValidationException:
        return ValidationException(
            message=f"文档内容提取失败: {error_message}", code="DOCUMENT_CONTENT_EXTRACTION_FAILED", errors={}
        )

    @staticmethod
    def empty_document_content() -> ValidationException:
        return ValidationException(message="文档内容不能为空", code="EMPTY_DOCUMENT_CONTENT", errors={})

    @staticmethod
    def ai_filename_generation_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message=f"AI文件名生成失败: {error_message}", code="AI_FILENAME_GENERATION_FAILED", errors={}
        )

    @staticmethod
    def document_naming_processing_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message=f"文档处理和命名生成失败: {error_message}", code="DOCUMENT_NAMING_PROCESSING_FAILED", errors={}
        )

    @staticmethod
    def unsupported_audio_format(file_ext: str, supported_formats: list[Any]) -> ValidationException:
        return ValidationException(message=f"不支持的音频格式: {file_ext}", code="UNSUPPORTED_AUDIO_FORMAT", errors={})

    @staticmethod
    def audio_transcription_failed(error_message: str) -> BusinessException:
        return BusinessException(message=f"音频转录失败: {error_message}", code="AUDIO_TRANSCRIPTION_FAILED", errors={})

    @staticmethod
    def missing_file_name() -> ValidationException:
        return ValidationException(message="上传文件缺少文件名", code="MISSING_FILE_NAME", errors={})

    @staticmethod
    def system_metrics_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message=f"获取系统性能指标失败: {error_message}", code="SYSTEM_METRICS_FAILED", errors={}
        )

    @staticmethod
    def token_acquisition_metrics_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message=f"获取Token获取性能指标失败: {error_message}", code="TOKEN_ACQUISITION_METRICS_FAILED", errors={}
        )

    @staticmethod
    def api_performance_metrics_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message=f"获取API性能指标失败: {error_message}", code="API_PERFORMANCE_METRICS_FAILED", errors={}
        )

    @staticmethod
    def invalid_days_parameter() -> ValidationException:
        return ValidationException(message="保留天数必须大于0", code="INVALID_DAYS_PARAMETER", errors={})

    @staticmethod
    def no_records_selected() -> ValidationException:
        return ValidationException(message="没有选中任何记录", code="NO_RECORDS_SELECTED", errors={})

    @staticmethod
    def cleanup_records_failed() -> BusinessException:
        return BusinessException(message="清理历史记录失败", code="CLEANUP_RECORDS_FAILED", errors={})

    @staticmethod
    def export_csv_failed() -> BusinessException:
        return BusinessException(message="导出CSV文件失败", code="EXPORT_CSV_FAILED", errors={})

    @staticmethod
    def performance_analysis_failed() -> BusinessException:
        return BusinessException(message="性能数据分析失败", code="PERFORMANCE_ANALYSIS_FAILED", errors={})

    @staticmethod
    def get_dashboard_stats_failed() -> BusinessException:
        return BusinessException(message="获取仪表板统计数据失败", code="GET_DASHBOARD_STATS_FAILED", errors={})

    @staticmethod
    def no_quotes_selected() -> ValidationException:
        return ValidationException(message="没有选中任何询价任务", code="NO_QUOTES_SELECTED", errors={})

    @staticmethod
    def no_executable_quotes() -> ValidationException:
        return ValidationException(message="没有找到可执行的询价任务", code="NO_EXECUTABLE_QUOTES", errors={})

    @staticmethod
    def execute_quotes_failed() -> BusinessException:
        return BusinessException(message="批量执行询价任务失败", code="EXECUTE_QUOTES_FAILED", errors={})

    @staticmethod
    def retry_failed_quotes_failed() -> BusinessException:
        return BusinessException(message="重试失败询价任务失败", code="RETRY_FAILED_QUOTES_FAILED", errors={})

    @staticmethod
    def get_quote_stats_failed() -> BusinessException:
        return BusinessException(message="获取询价统计数据失败", code="GET_QUOTE_STATS_FAILED", errors={})

    @staticmethod
    def no_quote_configs() -> ValidationException:
        return ValidationException(message="没有提供询价配置", code="NO_QUOTE_CONFIGS", errors={})

    @staticmethod
    def missing_preserve_amount() -> ValidationException:
        return ValidationException(message="缺少保全金额", code="MISSING_PRESERVE_AMOUNT", errors={})

    @staticmethod
    def empty_site_name() -> ValidationException:
        return ValidationException(message="网站名称不能为空", code="EMPTY_SITE_NAME", errors={})

    @staticmethod
    def empty_account_list() -> ValidationException:
        return ValidationException(message="没有可用账号", code="EMPTY_ACCOUNT_LIST", errors={})

    @staticmethod
    def unsupported_file_format(file_ext: str, supported_formats: list[str] | None = None) -> ValidationException:
        fmt: list[str] = supported_formats if supported_formats is not None else []
        return ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={
                "file": f"不支持 {file_ext} 格式,请上传 PDF 或图片(jpg, jpeg, png)",
                "supported_formats": fmt,
            },
        )

    @staticmethod
    def file_not_found(file_path: str) -> ValidationException:
        return ValidationException(
            message="文件不存在", code="FILE_NOT_FOUND", errors={"file": f"文件 {file_path} 不存在"}
        )

    @staticmethod
    def text_extraction_failed(error_message: str, file_path: str | None = None) -> ValidationException:
        errors = {"error_message": error_message}
        if file_path:
            errors["file_path"] = file_path
        return ValidationException(message="文本提取失败", code="TEXT_EXTRACTION_FAILED", errors=errors)

    @staticmethod
    def ai_service_unavailable(
        service_name: str = "Ollama", error_message: str | None = None
    ) -> ServiceUnavailableError:
        errors = {"service": f"{service_name} 服务暂时不可用,请稍后重试"}
        if error_message:
            errors["error_message"] = error_message
        return ServiceUnavailableError(
            message="AI 服务暂时不可用", code="AI_SERVICE_UNAVAILABLE", errors=errors, service_name=service_name
        )

    @staticmethod
    def recognition_timeout(timeout_seconds: float, operation: str | None = None) -> RecognitionTimeoutError:
        errors = {"timeout": f"识别超时({timeout_seconds}秒),请重试"}
        if operation:
            errors["operation"] = operation
        return RecognitionTimeoutError(
            message="识别超时,请重试", code="RECOGNITION_TIMEOUT", errors=errors, timeout_seconds=timeout_seconds
        )

    @staticmethod
    def document_classification_failed(error_message: str) -> BusinessException:
        return BusinessException(
            message="文书分类失败", code="DOCUMENT_CLASSIFICATION_FAILED", errors={"error_message": error_message}
        )

    @staticmethod
    def info_extraction_failed(error_message: str, document_type: str | None = None) -> BusinessException:
        errors = {"error_message": error_message}
        if document_type:
            errors["document_type"] = document_type
        return BusinessException(message="信息提取失败", code="INFO_EXTRACTION_FAILED", errors=errors)

    @staticmethod
    def case_binding_failed(case_number: str, error_message: str) -> BusinessException:
        return BusinessException(message="案件绑定失败", code="CASE_BINDING_FAILED", errors={})

    @staticmethod
    def case_not_found_for_binding(case_number: str) -> NotFoundError:
        return NotFoundError(
            message=f"未找到案号 {case_number} 对应的案件", code="CASE_NOT_FOUND", errors={"case_number": case_number}
        )
