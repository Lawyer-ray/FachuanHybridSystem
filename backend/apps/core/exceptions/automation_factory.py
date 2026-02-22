"""
Automation 模块异常工厂类
"""

from __future__ import annotations

from typing import Any

from .base import BusinessException
from .common import NotFoundError, ValidationException
from .external import RecognitionTimeoutError, ServiceUnavailableError

__all__: list[str] = ["AutomationExceptions"]


class AutomationExceptions:
    """Automation模块标准化异常工具类"""

    # ==================== 验证码相关异常 ====================

    @classmethod
    def captcha_recognition_failed(
        cls, details: str | None = None, processing_time: float | None = None
    ) -> ValidationException:
        """验证码识别失败异常"""
        errors: dict[str, Any] = {}
        if details:
            errors["details"] = details
        if processing_time is not None:
            errors["processing_time"] = processing_time

        return ValidationException(message="验证码识别失败", code="CAPTCHA_RECOGNITION_FAILED", errors=errors)

    @classmethod
    def captcha_recognition_error(
        cls, error_message: str, original_exception: Exception | None = None
    ) -> ValidationException:
        """验证码识别异常"""
        errors: dict[str, Any] = {"error_message": error_message}
        if original_exception:
            errors["original_error"] = str(original_exception)

        return ValidationException(message="验证码识别异常", code="CAPTCHA_RECOGNITION_ERROR", errors=errors)

    # ==================== Token相关异常 ====================

    @classmethod
    def token_acquisition_failed(
        cls, reason: str, site_name: str | None = None, account: str | None = None
    ) -> BusinessException:
        """Token获取失败异常"""
        errors: dict[str, Any] = {"reason": reason}
        if site_name:
            errors["site_name"] = site_name
        if account:
            errors["account"] = account

        return BusinessException(message="Token获取失败", code="TOKEN_ACQUISITION_FAILED", errors=errors)

    @classmethod
    def no_available_account_error(cls, site_name: str) -> ValidationException:
        """没有可用账号异常"""
        return ValidationException(
            message=f"网站 {site_name} 没有可用账号", code="NO_AVAILABLE_ACCOUNT", errors={"site_name": site_name}
        )

    @classmethod
    def invalid_credential_error(cls, credential_id: int) -> ValidationException:
        """无效凭证异常"""
        return ValidationException(
            message=f"指定的凭证ID不存在: {credential_id}",
            code="INVALID_CREDENTIAL_ID",
            errors={"credential_id": credential_id},
        )

    @classmethod
    def login_timeout_error(
        cls, timeout_seconds: int, site_name: str | None = None, account: str | None = None
    ) -> BusinessException:
        """登录超时异常"""
        errors: dict[str, Any] = {"timeout_seconds": timeout_seconds}
        if site_name:
            errors["site_name"] = site_name
        if account:
            errors["account"] = account

        return BusinessException(message=f"登录超时({timeout_seconds}秒)", code="LOGIN_TIMEOUT", errors=errors)

    # ==================== 文档相关异常 ====================

    @classmethod
    def document_not_found(cls, document_id: int) -> NotFoundError:
        """文档不存在异常"""
        return NotFoundError(message="文档不存在", code="DOCUMENT_NOT_FOUND", errors={"document_id": document_id})

    @classmethod
    def missing_required_fields(cls, missing_fields: list[str]) -> ValidationException:
        """缺少必需字段异常"""
        return ValidationException(
            message=f"缺少必需字段: {', '.join(missing_fields)}",
            code="MISSING_REQUIRED_FIELDS",
            errors={"missing_fields": missing_fields},
        )

    @classmethod
    def invalid_download_status(cls, status: str, valid_statuses: list[str]) -> ValidationException:
        """无效下载状态异常"""
        return ValidationException(
            message=f"无效的下载状态: {status}",
            code="INVALID_DOWNLOAD_STATUS",
            errors={"invalid_status": status, "valid_statuses": valid_statuses},
        )

    @classmethod
    def create_document_failed(cls, error_message: str, api_data: dict[str, Any] | None = None) -> BusinessException:
        """创建文档失败异常"""
        errors: dict[str, Any] = {"error_message": error_message}
        if api_data:
            errors["api_data_keys"] = list(api_data.keys())

        return BusinessException(
            message=f"创建文书记录失败: {error_message}", code="CREATE_DOCUMENT_FAILED", errors=errors
        )

    # ==================== 文档处理相关异常 ====================

    @classmethod
    def pdf_processing_failed(cls, error_message: str) -> ValidationException:
        """PDF处理失败异常"""
        return ValidationException(
            message=f"PDF文件处理失败: {error_message}",
            code="PDF_PROCESSING_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def docx_processing_failed(cls, error_message: str) -> ValidationException:
        """DOCX处理失败异常"""
        return ValidationException(
            message=f"DOCX文件处理失败: {error_message}",
            code="DOCX_PROCESSING_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def image_ocr_failed(cls, error_message: str) -> ValidationException:
        """图片OCR失败异常"""
        return ValidationException(
            message=f"图片OCR处理失败: {error_message}",
            code="IMAGE_OCR_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def document_content_extraction_failed(cls, error_message: str) -> ValidationException:
        """文档内容提取失败异常"""
        return ValidationException(
            message=f"文档内容提取失败: {error_message}",
            code="DOCUMENT_CONTENT_EXTRACTION_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def empty_document_content(cls) -> ValidationException:
        """文档内容为空异常"""
        return ValidationException(message="文档内容不能为空", code="EMPTY_DOCUMENT_CONTENT", errors={})

    # ==================== AI相关异常 ====================

    @classmethod
    def ai_filename_generation_failed(cls, error_message: str) -> BusinessException:
        """AI文件名生成失败异常"""
        return BusinessException(
            message=f"AI文件名生成失败: {error_message}",
            code="AI_FILENAME_GENERATION_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def document_naming_processing_failed(cls, error_message: str) -> BusinessException:
        """文档处理和命名生成失败异常"""
        return BusinessException(
            message=f"文档处理和命名生成失败: {error_message}",
            code="DOCUMENT_NAMING_PROCESSING_FAILED",
            errors={"error_message": error_message},
        )

    # ==================== 语音相关异常 ====================

    @classmethod
    def unsupported_audio_format(cls, file_ext: str, supported_formats: list[str]) -> ValidationException:
        """不支持的音频格式异常"""
        return ValidationException(
            message=f"不支持的音频格式: {file_ext}",
            code="UNSUPPORTED_AUDIO_FORMAT",
            errors={"file_extension": file_ext, "supported_formats": supported_formats},
        )

    @classmethod
    def audio_transcription_failed(cls, error_message: str) -> BusinessException:
        """音频转录失败异常"""
        return BusinessException(
            message=f"音频转录失败: {error_message}",
            code="AUDIO_TRANSCRIPTION_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def missing_file_name(cls) -> ValidationException:
        """缺少文件名异常"""
        return ValidationException(message="上传文件缺少文件名", code="MISSING_FILE_NAME", errors={})

    # ==================== 性能监控相关异常 ====================

    @classmethod
    def system_metrics_failed(cls, error_message: str) -> BusinessException:
        """系统性能指标获取失败异常"""
        return BusinessException(
            message=f"获取系统性能指标失败: {error_message}",
            code="SYSTEM_METRICS_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def token_acquisition_metrics_failed(cls, error_message: str) -> BusinessException:
        """Token获取性能指标失败异常"""
        return BusinessException(
            message=f"获取Token获取性能指标失败: {error_message}",
            code="TOKEN_ACQUISITION_METRICS_FAILED",
            errors={"error_message": error_message},
        )

    @classmethod
    def api_performance_metrics_failed(cls, error_message: str) -> BusinessException:
        """API性能指标获取失败异常"""
        return BusinessException(
            message=f"获取API性能指标失败: {error_message}",
            code="API_PERFORMANCE_METRICS_FAILED",
            errors={"error_message": error_message},
        )

    # ==================== Admin相关异常 ====================

    @classmethod
    def invalid_days_parameter(cls) -> ValidationException:
        """无效天数参数异常"""
        return ValidationException(message="保留天数必须大于0", code="INVALID_DAYS_PARAMETER", errors={})

    @classmethod
    def no_records_selected(cls) -> ValidationException:
        """没有选中记录异常"""
        return ValidationException(message="没有选中任何记录", code="NO_RECORDS_SELECTED", errors={})

    @classmethod
    def cleanup_records_failed(cls) -> BusinessException:
        """清理记录失败异常"""
        return BusinessException(message="清理历史记录失败", code="CLEANUP_RECORDS_FAILED", errors={})

    @classmethod
    def export_csv_failed(cls) -> BusinessException:
        """导出CSV失败异常"""
        return BusinessException(message="导出CSV文件失败", code="EXPORT_CSV_FAILED", errors={})

    @classmethod
    def performance_analysis_failed(cls) -> BusinessException:
        """性能分析失败异常"""
        return BusinessException(message="性能数据分析失败", code="PERFORMANCE_ANALYSIS_FAILED", errors={})

    @classmethod
    def get_dashboard_stats_failed(cls) -> BusinessException:
        """获取仪表板统计失败异常"""
        return BusinessException(message="获取仪表板统计数据失败", code="GET_DASHBOARD_STATS_FAILED", errors={})

    # ==================== 询价相关异常 ====================

    @classmethod
    def no_quotes_selected(cls) -> ValidationException:
        """没有选中询价任务异常"""
        return ValidationException(message="没有选中任何询价任务", code="NO_QUOTES_SELECTED", errors={})

    @classmethod
    def no_executable_quotes(cls) -> ValidationException:
        """没有可执行询价任务异常"""
        return ValidationException(message="没有找到可执行的询价任务", code="NO_EXECUTABLE_QUOTES", errors={})

    @classmethod
    def execute_quotes_failed(cls) -> BusinessException:
        """执行询价任务失败异常"""
        return BusinessException(message="批量执行询价任务失败", code="EXECUTE_QUOTES_FAILED", errors={})

    @classmethod
    def retry_failed_quotes_failed(cls) -> BusinessException:
        """重试失败询价任务失败异常"""
        return BusinessException(message="重试失败询价任务失败", code="RETRY_FAILED_QUOTES_FAILED", errors={})

    @classmethod
    def get_quote_stats_failed(cls) -> BusinessException:
        """获取询价统计失败异常"""
        return BusinessException(message="获取询价统计数据失败", code="GET_QUOTE_STATS_FAILED", errors={})

    @classmethod
    def no_quote_configs(cls) -> ValidationException:
        """没有询价配置异常"""
        return ValidationException(message="没有提供询价配置", code="NO_QUOTE_CONFIGS", errors={})

    @classmethod
    def missing_preserve_amount(cls) -> ValidationException:
        """缺少保全金额异常"""
        return ValidationException(message="缺少保全金额", code="MISSING_PRESERVE_AMOUNT", errors={})

    # ==================== 通用参数验证异常 ====================

    @classmethod
    def empty_site_name(cls) -> ValidationException:
        """网站名称为空异常"""
        return ValidationException(message="网站名称不能为空", code="EMPTY_SITE_NAME", errors={})

    @classmethod
    def empty_account_list(cls) -> ValidationException:
        """账号列表为空异常"""
        return ValidationException(message="没有可用账号", code="EMPTY_ACCOUNT_LIST", errors={})

    # ==================== 文书识别相关异常 ====================

    @classmethod
    def unsupported_file_format(cls, file_ext: str, supported_formats: list[str] | None = None) -> ValidationException:
        """不支持的文件格式异常"""
        if supported_formats is None:
            supported_formats = [".pdf", ".jpg", ".jpeg", ".png"]
        return ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={
                "file": f"不支持 {file_ext} 格式,请上传 PDF 或图片(jpg, jpeg, png)",
                "supported_formats": supported_formats,
            },
        )

    @classmethod
    def file_not_found(cls, file_path: str) -> ValidationException:
        """文件不存在异常"""
        return ValidationException(
            message="文件不存在", code="FILE_NOT_FOUND", errors={"file": f"文件 {file_path} 不存在"}
        )

    @classmethod
    def text_extraction_failed(cls, error_message: str, file_path: str | None = None) -> ValidationException:
        """文本提取失败异常"""
        errors: dict[str, Any] = {"error_message": error_message}
        if file_path:
            errors["file_path"] = file_path
        return ValidationException(message="文本提取失败", code="TEXT_EXTRACTION_FAILED", errors=errors)

    @classmethod
    def ai_service_unavailable(
        cls, service_name: str = "Ollama", error_message: str | None = None
    ) -> ServiceUnavailableError:
        """AI 服务不可用异常"""
        errors: dict[str, Any] = {"service": f"{service_name} 服务暂时不可用,请稍后重试"}
        if error_message:
            errors["error_message"] = error_message
        return ServiceUnavailableError(
            message="AI 服务暂时不可用", code="AI_SERVICE_UNAVAILABLE", errors=errors, service_name=service_name
        )

    @classmethod
    def recognition_timeout(cls, timeout_seconds: float, operation: str | None = None) -> RecognitionTimeoutError:
        """识别超时异常"""
        errors: dict[str, Any] = {"timeout": f"识别超时({timeout_seconds}秒),请重试"}
        if operation:
            errors["operation"] = operation
        return RecognitionTimeoutError(
            message="识别超时,请重试", code="RECOGNITION_TIMEOUT", errors=errors, timeout_seconds=timeout_seconds
        )

    @classmethod
    def document_classification_failed(cls, error_message: str) -> BusinessException:
        """文书分类失败异常"""
        return BusinessException(
            message="文书分类失败", code="DOCUMENT_CLASSIFICATION_FAILED", errors={"error_message": error_message}
        )

    @classmethod
    def info_extraction_failed(cls, error_message: str, document_type: str | None = None) -> BusinessException:
        """信息提取失败异常"""
        errors: dict[str, Any] = {"error_message": error_message}
        if document_type:
            errors["document_type"] = document_type
        return BusinessException(message="信息提取失败", code="INFO_EXTRACTION_FAILED", errors=errors)

    @classmethod
    def case_binding_failed(cls, case_number: str, error_message: str) -> BusinessException:
        """案件绑定失败异常"""
        return BusinessException(
            message="案件绑定失败",
            code="CASE_BINDING_FAILED",
            errors={"case_number": case_number, "error_message": error_message},
        )

    @classmethod
    def case_not_found_for_binding(cls, case_number: str) -> NotFoundError:
        """案件未找到(绑定时)异常"""
        return NotFoundError(
            message=f"未找到案号 {case_number} 对应的案件", code="CASE_NOT_FOUND", errors={"case_number": case_number}
        )
