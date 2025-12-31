"""
统一异常处理模块
定义业务异常和全局异常处理器
"""
from typing import Any, Dict, Optional, List
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError
from django.http import Http404
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, ObjectDoesNotExist
import logging

logger = logging.getLogger("api")


class BusinessException(Exception):
    """
    业务异常基类

    所有自定义业务异常都应该继承此类

    Attributes:
        message: 错误消息（用户可读）
        code: 错误码（用于前端判断）
        errors: 结构化错误详情（字段级别的错误）
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        """
        初始化业务异常

        Args:
            message: 错误消息（用户可读）
            code: 错误码（用于前端判断），默认使用类名
            errors: 结构化错误详情（字段级别的错误）
        """
        self.message = message
        self.code = code or self.__class__.__name__
        self.errors = errors or {}
        super().__init__(message)

    def __str__(self) -> str:
        """返回字符串表示"""
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        """返回详细的字符串表示"""
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r}, errors={self.errors!r})"

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于 API 响应）

        Returns:
            包含 error、code、errors 字段的字典
        """
        return {
            "error": self.message,
            "code": self.code,
            "errors": self.errors
        }


# 保留旧的 BusinessError 作为别名，以保持向后兼容
class BusinessError(BusinessException):
    """业务逻辑异常基类（向后兼容）"""
    def __init__(self, message: str, code: str = "BUSINESS_ERROR", status: int = 400):
        super().__init__(message, code)
        self.status = status


class ValidationException(BusinessException):
    """
    验证异常

    使用场景：
    - 数据格式不正确
    - 业务规则验证失败
    - 字段值不符合要求

    HTTP 状态码：400
    """

    def __init__(
        self,
        message: str = "数据验证失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "VALIDATION_ERROR",
            errors=errors
        )


class PermissionDenied(BusinessException):
    """
    权限拒绝异常

    使用场景：
    - 用户无权限执行操作
    - 访问被拒绝的资源

    HTTP 状态码：403
    """

    def __init__(
        self,
        message: str = "无权限执行该操作",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "PERMISSION_DENIED",
            errors=errors
        )


class NotFoundError(BusinessException):
    """
    资源不存在异常

    使用场景：
    - 查询的资源不存在
    - ID 无效

    HTTP 状态码：404
    """

    def __init__(
        self,
        message: str = "资源不存在",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "NOT_FOUND",
            errors=errors
        )


class ConflictError(BusinessException):
    """
    资源冲突异常

    使用场景：
    - 资源已存在（重复创建）
    - 资源状态冲突
    - 并发修改冲突

    HTTP 状态码：409
    """

    def __init__(
        self,
        message: str = "资源冲突",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "CONFLICT",
            errors=errors
        )


class AuthenticationError(BusinessException):
    """
    认证失败异常

    使用场景：
    - 登录失败
    - Token 无效
    - 会话过期

    HTTP 状态码：401
    """

    def __init__(
        self,
        message: str = "认证失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "AUTHENTICATION_ERROR",
            errors=errors
        )


class RateLimitError(BusinessException):
    """
    频率限制异常

    使用场景：
    - 请求过于频繁
    - 超过配额限制

    HTTP 状态码：429
    """

    def __init__(
        self,
        message: str = "请求过于频繁",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "RATE_LIMIT_ERROR",
            errors=errors
        )


class ExternalServiceError(BusinessException):
    """
    外部服务错误

    使用场景：
    - 第三方 API 调用失败
    - 外部服务不可用

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "外部服务错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "EXTERNAL_SERVICE_ERROR",
            errors=errors
        )


class ServiceUnavailableError(ExternalServiceError):
    """
    服务不可用异常

    使用场景：
    - AI 服务（如 Ollama）不可用
    - 依赖服务暂时不可用
    - 服务维护中

    HTTP 状态码：503
    """

    def __init__(
        self,
        message: str = "服务暂时不可用",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        service_name: Optional[str] = None
    ):
        if service_name:
            errors = errors or {}
            errors["service"] = service_name
        super().__init__(
            message=message,
            code=code or "SERVICE_UNAVAILABLE",
            errors=errors
        )
        self.service_name = service_name


class RecognitionTimeoutError(ExternalServiceError):
    """
    识别超时异常

    使用场景：
    - AI 识别超时
    - OCR 处理超时
    - 文档处理超时

    HTTP 状态码：504
    """

    def __init__(
        self,
        message: str = "识别超时",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None
    ):
        if timeout_seconds is not None:
            errors = errors or {}
            errors["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=message,
            code=code or "RECOGNITION_TIMEOUT",
            errors=errors
        )
        self.timeout_seconds = timeout_seconds


class TokenError(BusinessException):
    """
    Token 错误

    使用场景：
    - Token 不存在
    - Token 已过期
    - Token 无效

    HTTP 状态码：401
    """

    def __init__(
        self,
        message: str = "Token 错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "TOKEN_ERROR",
            errors=errors
        )


class APIError(ExternalServiceError):
    """
    API 调用错误

    使用场景：
    - API 返回错误状态码
    - API 响应格式错误
    - API 业务逻辑错误

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "API 调用错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "API_ERROR",
            errors=errors
        )


class NetworkError(ExternalServiceError):
    """
    网络错误

    使用场景：
    - 网络连接失败
    - 请求超时
    - 连接被拒绝

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "网络错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "NETWORK_ERROR",
            errors=errors
        )


class AutoTokenAcquisitionError(ExternalServiceError):
    """
    自动Token获取基础异常

    使用场景：
    - 自动Token获取流程中的各种错误
    - 作为其他Token获取异常的基类

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "自动Token获取失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "AUTO_TOKEN_ACQUISITION_ERROR",
            errors=errors
        )


class LoginFailedError(AutoTokenAcquisitionError):
    """
    登录失败异常

    使用场景：
    - 账号密码错误
    - 验证码识别失败
    - 登录流程异常

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "登录失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        attempts: Optional[List[Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "LOGIN_FAILED",
            errors=errors
        )
        self.attempts = attempts or []


class NoAvailableAccountError(AutoTokenAcquisitionError):
    """
    无可用账号异常

    使用场景：
    - 没有配置账号凭证
    - 所有账号都已失效
    - 所有账号都在黑名单中

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "无可用账号",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "NO_AVAILABLE_ACCOUNT",
            errors=errors
        )


class TokenAcquisitionTimeoutError(AutoTokenAcquisitionError):
    """
    Token获取超时异常

    使用场景：
    - 登录过程超时
    - Token获取流程超时

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "Token获取超时",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "TOKEN_ACQUISITION_TIMEOUT",
            errors=errors
        )


class CaptchaRecognitionError(ExternalServiceError):
    """
    验证码识别错误

    使用场景：
    - 验证码识别失败
    - 验证码图片格式不支持
    - 验证码识别服务异常

    HTTP 状态码：502
    """

    def __init__(
        self,
        message: str = "验证码识别失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code or "CAPTCHA_RECOGNITION_ERROR",
            errors=errors
        )


# 保留旧的异常类作为别名，以保持向后兼容
class ForbiddenError(PermissionDenied):
    """无权限访问（向后兼容）"""
    def __init__(self, message: str = "无权限访问"):
        super().__init__(message)
        self.status = 403


class UnauthorizedError(AuthenticationError):
    """未认证（向后兼容）"""
    def __init__(self, message: str = "请先登录"):
        super().__init__(message)
        self.status = 401


# ==================== 群聊相关异常（从 cases.exceptions 迁移） ====================

class ChatProviderException(BusinessException):
    """群聊提供者异常基类"""
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "CHAT_PROVIDER_ERROR", errors=errors)
        self.error_code = error_code
        self.platform = platform


class UnsupportedPlatformException(ChatProviderException):
    """不支持的平台异常"""
    
    def __init__(
        self,
        message: str = "不支持的群聊平台",
        platform: Optional[str] = None,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code or "UNSUPPORTED_PLATFORM", errors=errors, platform=platform)


class ChatCreationException(ChatProviderException):
    """群聊创建失败异常"""
    
    def __init__(
        self,
        message: str = "群聊创建失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "CHAT_CREATION_ERROR", errors=errors, error_code=error_code, platform=platform)


class MessageSendException(ChatProviderException):
    """消息发送失败异常"""
    
    def __init__(
        self,
        message: str = "消息发送失败",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "MESSAGE_SEND_ERROR", errors=errors, error_code=error_code, platform=platform)
        self.chat_id = chat_id


class ConfigurationException(ChatProviderException):
    """配置错误异常"""
    
    def __init__(
        self,
        message: str = "群聊平台配置错误",
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        platform: Optional[str] = None,
        missing_config: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "CONFIGURATION_ERROR", errors=errors, platform=platform)
        self.missing_config = missing_config


class OwnerSettingException(ChatProviderException):
    """群主设置异常基类"""
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        platform: Optional[str] = None,
        owner_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "OWNER_SETTING_ERROR", errors=errors, error_code=error_code, platform=platform)
        self.owner_id = owner_id
        self.chat_id = chat_id


class OwnerPermissionException(OwnerSettingException):
    """群主权限异常"""
    def __init__(self, message: str = "群主权限不足", **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_PERMISSION_ERROR"), **kwargs)


class OwnerNotFoundException(OwnerSettingException):
    """群主用户不存在异常"""
    def __init__(self, message: str = "群主用户不存在", **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_NOT_FOUND"), **kwargs)


class OwnerValidationException(OwnerSettingException):
    """群主验证异常"""
    def __init__(self, message: str = "群主验证失败", **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_VALIDATION_ERROR"), **kwargs)


class OwnerRetryException(OwnerSettingException):
    """群主设置重试异常"""
    def __init__(self, message: str = "群主设置重试失败", retry_count: Optional[int] = None, max_retries: Optional[int] = None, **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_RETRY_ERROR"), **kwargs)
        self.retry_count = retry_count
        self.max_retries = max_retries


class OwnerTimeoutException(OwnerSettingException):
    """群主设置超时异常"""
    def __init__(self, message: str = "群主设置操作超时", timeout_seconds: Optional[float] = None, **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_TIMEOUT_ERROR"), **kwargs)
        self.timeout_seconds = timeout_seconds


class OwnerNetworkException(OwnerSettingException):
    """群主设置网络异常"""
    def __init__(self, message: str = "群主设置网络错误", network_error: Optional[str] = None, **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_NETWORK_ERROR"), **kwargs)
        self.network_error = network_error


class OwnerConfigException(OwnerSettingException):
    """群主配置异常"""
    def __init__(self, message: str = "群主配置错误", config_key: Optional[str] = None, **kwargs):
        super().__init__(message=message, code=kwargs.pop("code", "OWNER_CONFIG_ERROR"), **kwargs)
        self.config_key = config_key


# ==================== Automation 模块异常工厂类 ====================

class AutomationExceptions:
    """Automation模块标准化异常工具类"""
    
    # ==================== 验证码相关异常 ====================
    
    @staticmethod
    def captcha_recognition_failed(
        details: Optional[str] = None,
        processing_time: Optional[float] = None
    ) -> ValidationException:
        """验证码识别失败异常"""
        errors = {}
        if details:
            errors["details"] = details
        if processing_time is not None:
            errors["processing_time"] = processing_time
            
        return ValidationException(
            message="验证码识别失败",
            code="CAPTCHA_RECOGNITION_FAILED",
            errors=errors
        )
    
    @staticmethod
    def captcha_recognition_error(
        error_message: str,
        original_exception: Optional[Exception] = None
    ) -> ValidationException:
        """验证码识别异常"""
        errors = {"error_message": error_message}
        if original_exception:
            errors["original_error"] = str(original_exception)
            
        return ValidationException(
            message="验证码识别异常",
            code="CAPTCHA_RECOGNITION_ERROR",
            errors=errors
        )
    
    # ==================== Token相关异常 ====================
    
    @staticmethod
    def token_acquisition_failed(
        reason: str,
        site_name: Optional[str] = None,
        account: Optional[str] = None
    ) -> BusinessException:
        """Token获取失败异常"""
        errors = {"reason": reason}
        if site_name:
            errors["site_name"] = site_name
        if account:
            errors["account"] = account
            
        return BusinessException(
            message="Token获取失败",
            code="TOKEN_ACQUISITION_FAILED",
            errors=errors
        )
    
    @staticmethod
    def no_available_account_error(
        site_name: str
    ) -> ValidationException:
        """没有可用账号异常"""
        return ValidationException(
            message=f"网站 {site_name} 没有可用账号",
            code="NO_AVAILABLE_ACCOUNT",
            errors={"site_name": site_name}
        )
    
    @staticmethod
    def invalid_credential_error(
        credential_id: int
    ) -> ValidationException:
        """无效凭证异常"""
        return ValidationException(
            message=f"指定的凭证ID不存在: {credential_id}",
            code="INVALID_CREDENTIAL_ID",
            errors={"credential_id": credential_id}
        )
    
    @staticmethod
    def login_timeout_error(
        timeout_seconds: int,
        site_name: Optional[str] = None,
        account: Optional[str] = None
    ) -> BusinessException:
        """登录超时异常"""
        errors = {"timeout_seconds": timeout_seconds}
        if site_name:
            errors["site_name"] = site_name
        if account:
            errors["account"] = account
            
        return BusinessException(
            message=f"登录超时（{timeout_seconds}秒）",
            code="LOGIN_TIMEOUT",
            errors=errors
        )
    
    # ==================== 文档相关异常 ====================
    
    @staticmethod
    def document_not_found(
        document_id: int
    ) -> NotFoundError:
        """文档不存在异常"""
        return NotFoundError(
            message="文档不存在",
            code="DOCUMENT_NOT_FOUND",
            errors={"document_id": document_id}
        )
    
    @staticmethod
    def missing_required_fields(
        missing_fields: list
    ) -> ValidationException:
        """缺少必需字段异常"""
        return ValidationException(
            message=f"缺少必需字段: {', '.join(missing_fields)}",
            code="MISSING_REQUIRED_FIELDS",
            errors={"missing_fields": missing_fields}
        )
    
    @staticmethod
    def invalid_download_status(
        status: str,
        valid_statuses: list
    ) -> ValidationException:
        """无效下载状态异常"""
        return ValidationException(
            message=f"无效的下载状态: {status}",
            code="INVALID_DOWNLOAD_STATUS",
            errors={
                "invalid_status": status,
                "valid_statuses": valid_statuses
            }
        )
    
    @staticmethod
    def create_document_failed(
        error_message: str,
        api_data: Optional[Dict[str, Any]] = None
    ) -> BusinessException:
        """创建文档失败异常"""
        errors = {"error_message": error_message}
        if api_data:
            errors["api_data_keys"] = list(api_data.keys())
            
        return BusinessException(
            message=f"创建文书记录失败: {error_message}",
            code="CREATE_DOCUMENT_FAILED",
            errors=errors
        )
    
    # ==================== 文档处理相关异常 ====================
    
    @staticmethod
    def pdf_processing_failed(
        error_message: str
    ) -> ValidationException:
        """PDF处理失败异常"""
        return ValidationException(
            message=f"PDF文件处理失败: {error_message}",
            code="PDF_PROCESSING_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def docx_processing_failed(
        error_message: str
    ) -> ValidationException:
        """DOCX处理失败异常"""
        return ValidationException(
            message=f"DOCX文件处理失败: {error_message}",
            code="DOCX_PROCESSING_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def image_ocr_failed(
        error_message: str
    ) -> ValidationException:
        """图片OCR失败异常"""
        return ValidationException(
            message=f"图片OCR处理失败: {error_message}",
            code="IMAGE_OCR_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def document_content_extraction_failed(
        error_message: str
    ) -> ValidationException:
        """文档内容提取失败异常"""
        return ValidationException(
            message=f"文档内容提取失败: {error_message}",
            code="DOCUMENT_CONTENT_EXTRACTION_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def empty_document_content() -> ValidationException:
        """文档内容为空异常"""
        return ValidationException(
            message="文档内容不能为空",
            code="EMPTY_DOCUMENT_CONTENT",
            errors={}
        )
    
    # ==================== AI相关异常 ====================
    
    @staticmethod
    def ai_filename_generation_failed(
        error_message: str
    ) -> BusinessException:
        """AI文件名生成失败异常"""
        return BusinessException(
            message=f"AI文件名生成失败: {error_message}",
            code="AI_FILENAME_GENERATION_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def document_naming_processing_failed(
        error_message: str
    ) -> BusinessException:
        """文档处理和命名生成失败异常"""
        return BusinessException(
            message=f"文档处理和命名生成失败: {error_message}",
            code="DOCUMENT_NAMING_PROCESSING_FAILED",
            errors={"error_message": error_message}
        )
    
    # ==================== 语音相关异常 ====================
    
    @staticmethod
    def unsupported_audio_format(
        file_ext: str,
        supported_formats: list
    ) -> ValidationException:
        """不支持的音频格式异常"""
        return ValidationException(
            message=f"不支持的音频格式: {file_ext}",
            code="UNSUPPORTED_AUDIO_FORMAT",
            errors={
                "file_extension": file_ext,
                "supported_formats": supported_formats
            }
        )
    
    @staticmethod
    def audio_transcription_failed(
        error_message: str
    ) -> BusinessException:
        """音频转录失败异常"""
        return BusinessException(
            message=f"音频转录失败: {error_message}",
            code="AUDIO_TRANSCRIPTION_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def missing_file_name() -> ValidationException:
        """缺少文件名异常"""
        return ValidationException(
            message="上传文件缺少文件名",
            code="MISSING_FILE_NAME",
            errors={}
        )
    
    # ==================== 性能监控相关异常 ====================
    
    @staticmethod
    def system_metrics_failed(
        error_message: str
    ) -> BusinessException:
        """系统性能指标获取失败异常"""
        return BusinessException(
            message=f"获取系统性能指标失败: {error_message}",
            code="SYSTEM_METRICS_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def token_acquisition_metrics_failed(
        error_message: str
    ) -> BusinessException:
        """Token获取性能指标失败异常"""
        return BusinessException(
            message=f"获取Token获取性能指标失败: {error_message}",
            code="TOKEN_ACQUISITION_METRICS_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def api_performance_metrics_failed(
        error_message: str
    ) -> BusinessException:
        """API性能指标获取失败异常"""
        return BusinessException(
            message=f"获取API性能指标失败: {error_message}",
            code="API_PERFORMANCE_METRICS_FAILED",
            errors={"error_message": error_message}
        )
    
    # ==================== Admin相关异常 ====================
    
    @staticmethod
    def invalid_days_parameter() -> ValidationException:
        """无效天数参数异常"""
        return ValidationException(
            message="保留天数必须大于0",
            code="INVALID_DAYS_PARAMETER",
            errors={}
        )
    
    @staticmethod
    def no_records_selected() -> ValidationException:
        """没有选中记录异常"""
        return ValidationException(
            message="没有选中任何记录",
            code="NO_RECORDS_SELECTED",
            errors={}
        )
    
    @staticmethod
    def cleanup_records_failed() -> BusinessException:
        """清理记录失败异常"""
        return BusinessException(
            message="清理历史记录失败",
            code="CLEANUP_RECORDS_FAILED",
            errors={}
        )
    
    @staticmethod
    def export_csv_failed() -> BusinessException:
        """导出CSV失败异常"""
        return BusinessException(
            message="导出CSV文件失败",
            code="EXPORT_CSV_FAILED",
            errors={}
        )
    
    @staticmethod
    def performance_analysis_failed() -> BusinessException:
        """性能分析失败异常"""
        return BusinessException(
            message="性能数据分析失败",
            code="PERFORMANCE_ANALYSIS_FAILED",
            errors={}
        )
    
    @staticmethod
    def get_dashboard_stats_failed() -> BusinessException:
        """获取仪表板统计失败异常"""
        return BusinessException(
            message="获取仪表板统计数据失败",
            code="GET_DASHBOARD_STATS_FAILED",
            errors={}
        )
    
    # ==================== 询价相关异常 ====================
    
    @staticmethod
    def no_quotes_selected() -> ValidationException:
        """没有选中询价任务异常"""
        return ValidationException(
            message="没有选中任何询价任务",
            code="NO_QUOTES_SELECTED",
            errors={}
        )
    
    @staticmethod
    def no_executable_quotes() -> ValidationException:
        """没有可执行询价任务异常"""
        return ValidationException(
            message="没有找到可执行的询价任务",
            code="NO_EXECUTABLE_QUOTES",
            errors={}
        )
    
    @staticmethod
    def execute_quotes_failed() -> BusinessException:
        """执行询价任务失败异常"""
        return BusinessException(
            message="批量执行询价任务失败",
            code="EXECUTE_QUOTES_FAILED",
            errors={}
        )
    
    @staticmethod
    def retry_failed_quotes_failed() -> BusinessException:
        """重试失败询价任务失败异常"""
        return BusinessException(
            message="重试失败询价任务失败",
            code="RETRY_FAILED_QUOTES_FAILED",
            errors={}
        )
    
    @staticmethod
    def get_quote_stats_failed() -> BusinessException:
        """获取询价统计失败异常"""
        return BusinessException(
            message="获取询价统计数据失败",
            code="GET_QUOTE_STATS_FAILED",
            errors={}
        )
    
    @staticmethod
    def no_quote_configs() -> ValidationException:
        """没有询价配置异常"""
        return ValidationException(
            message="没有提供询价配置",
            code="NO_QUOTE_CONFIGS",
            errors={}
        )
    
    @staticmethod
    def missing_preserve_amount() -> ValidationException:
        """缺少保全金额异常"""
        return ValidationException(
            message="缺少保全金额",
            code="MISSING_PRESERVE_AMOUNT",
            errors={}
        )
    
    # ==================== 通用参数验证异常 ====================
    
    @staticmethod
    def empty_site_name() -> ValidationException:
        """网站名称为空异常"""
        return ValidationException(
            message="网站名称不能为空",
            code="EMPTY_SITE_NAME",
            errors={}
        )
    
    @staticmethod
    def empty_account_list() -> ValidationException:
        """账号列表为空异常"""
        return ValidationException(
            message="没有可用账号",
            code="EMPTY_ACCOUNT_LIST",
            errors={}
        )
    
    # ==================== 文书识别相关异常 ====================
    
    @staticmethod
    def unsupported_file_format(
        file_ext: str,
        supported_formats: Optional[List[str]] = None
    ) -> ValidationException:
        """不支持的文件格式异常"""
        if supported_formats is None:
            supported_formats = ['.pdf', '.jpg', '.jpeg', '.png']
        return ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={
                "file": f"不支持 {file_ext} 格式，请上传 PDF 或图片（jpg, jpeg, png）",
                "supported_formats": supported_formats
            }
        )
    
    @staticmethod
    def file_not_found(file_path: str) -> ValidationException:
        """文件不存在异常"""
        return ValidationException(
            message="文件不存在",
            code="FILE_NOT_FOUND",
            errors={"file": f"文件 {file_path} 不存在"}
        )
    
    @staticmethod
    def text_extraction_failed(
        error_message: str,
        file_path: Optional[str] = None
    ) -> ValidationException:
        """文本提取失败异常"""
        errors = {"error_message": error_message}
        if file_path:
            errors["file_path"] = file_path
        return ValidationException(
            message="文本提取失败",
            code="TEXT_EXTRACTION_FAILED",
            errors=errors
        )
    
    @staticmethod
    def ai_service_unavailable(
        service_name: str = "Ollama",
        error_message: Optional[str] = None
    ) -> "ServiceUnavailableError":
        """AI 服务不可用异常"""
        errors = {"service": f"{service_name} 服务暂时不可用，请稍后重试"}
        if error_message:
            errors["error_message"] = error_message
        return ServiceUnavailableError(
            message="AI 服务暂时不可用",
            code="AI_SERVICE_UNAVAILABLE",
            errors=errors,
            service_name=service_name
        )
    
    @staticmethod
    def recognition_timeout(
        timeout_seconds: float,
        operation: Optional[str] = None
    ) -> "RecognitionTimeoutError":
        """识别超时异常"""
        errors = {"timeout": f"识别超时（{timeout_seconds}秒），请重试"}
        if operation:
            errors["operation"] = operation
        return RecognitionTimeoutError(
            message="识别超时，请重试",
            code="RECOGNITION_TIMEOUT",
            errors=errors,
            timeout_seconds=timeout_seconds
        )
    
    @staticmethod
    def document_classification_failed(
        error_message: str
    ) -> BusinessException:
        """文书分类失败异常"""
        return BusinessException(
            message="文书分类失败",
            code="DOCUMENT_CLASSIFICATION_FAILED",
            errors={"error_message": error_message}
        )
    
    @staticmethod
    def info_extraction_failed(
        error_message: str,
        document_type: Optional[str] = None
    ) -> BusinessException:
        """信息提取失败异常"""
        errors = {"error_message": error_message}
        if document_type:
            errors["document_type"] = document_type
        return BusinessException(
            message="信息提取失败",
            code="INFO_EXTRACTION_FAILED",
            errors=errors
        )
    
    @staticmethod
    def case_binding_failed(
        case_number: str,
        error_message: str
    ) -> BusinessException:
        """案件绑定失败异常"""
        return BusinessException(
            message="案件绑定失败",
            code="CASE_BINDING_FAILED",
            errors={
                "case_number": case_number,
                "error_message": error_message
            }
        )
    
    @staticmethod
    def case_not_found_for_binding(
        case_number: str
    ) -> NotFoundError:
        """案件未找到（绑定时）异常"""
        return NotFoundError(
            message=f"未找到案号 {case_number} 对应的案件",
            code="CASE_NOT_FOUND",
            errors={"case_number": case_number}
        )


def register_exception_handlers(api: NinjaAPI) -> None:
    """注册全局异常处理器"""

    # 1. 验证异常 - 400
    @api.exception_handler(ValidationException)
    def handle_validation_exception(request, exc: ValidationException):
        """处理验证异常"""
        logger.info(
            f"验证失败: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=400
        )

    # 2. 认证失败 - 401
    @api.exception_handler(AuthenticationError)
    def handle_authentication_error(request, exc: AuthenticationError):
        """处理认证失败"""
        logger.warning(
            f"认证失败: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=401
        )

    # 3. 权限拒绝 - 403
    @api.exception_handler(PermissionDenied)
    def handle_permission_denied_exception(request, exc: PermissionDenied):
        """处理权限拒绝"""
        logger.warning(
            f"权限拒绝: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, 'id', None) if hasattr(request, 'auth') else None
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=403
        )

    # 4. 资源不存在 - 404
    @api.exception_handler(NotFoundError)
    def handle_not_found_exception(request, exc: NotFoundError):
        """处理资源不存在"""
        logger.info(
            f"资源不存在: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=404
        )

    # 5. 资源冲突 - 409
    @api.exception_handler(ConflictError)
    def handle_conflict_exception(request, exc: ConflictError):
        """处理资源冲突"""
        logger.info(
            f"资源冲突: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=409
        )

    # 6. 频率限制 - 429
    @api.exception_handler(RateLimitError)
    def handle_rate_limit_exception(request, exc: RateLimitError):
        """处理频率限制"""
        logger.warning(
            f"频率限制: {exc.message}",
            extra={
                "code": exc.code,
                "path": request.path,
                "user_id": getattr(request.auth, 'id', None) if hasattr(request, 'auth') else None
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=429
        )

    # 7. 服务不可用 - 503
    @api.exception_handler(ServiceUnavailableError)
    def handle_service_unavailable_error(request, exc: ServiceUnavailableError):
        """处理服务不可用错误"""
        logger.error(
            f"服务不可用: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path,
                "service_name": getattr(exc, 'service_name', None)
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=503
        )

    # 8. 识别超时 - 504
    @api.exception_handler(RecognitionTimeoutError)
    def handle_recognition_timeout_error(request, exc: RecognitionTimeoutError):
        """处理识别超时错误"""
        logger.error(
            f"识别超时: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path,
                "timeout_seconds": getattr(exc, 'timeout_seconds', None)
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=504
        )

    # 9. 外部服务错误 - 502
    @api.exception_handler(ExternalServiceError)
    def handle_external_service_error(request, exc: ExternalServiceError):
        """处理外部服务错误"""
        logger.error(
            f"外部服务错误: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=502
        )

    # 10. 通用业务异常 - 400
    @api.exception_handler(BusinessException)
    def handle_business_exception(request, exc: BusinessException):
        """处理通用业务异常"""
        logger.warning(
            f"业务异常: {exc.message}",
            extra={
                "code": exc.code,
                "errors": exc.errors,
                "path": request.path
            }
        )
        return api.create_response(
            request,
            exc.to_dict(),
            status=400
        )

    # 向后兼容：处理旧的 BusinessError
    @api.exception_handler(BusinessError)
    def handle_business_error(request, exc: BusinessError):
        logger.warning(
            f"BusinessError: {exc.code} - {exc.message}",
            extra={"path": request.path, "method": request.method}
        )
        response = {"success": False, "code": exc.code, "message": exc.message}
        if hasattr(exc, 'errors') and exc.errors:
            response["errors"] = exc.errors
        status = getattr(exc, 'status', 400)
        return api.create_response(request, response, status=status)

    # Django 内置异常处理
    @api.exception_handler(Http404)
    def handle_404(request, exc: Http404):
        logger.info(f"404 Not Found: {request.path}")
        return api.create_response(
            request,
            {"error": "资源不存在", "code": "NOT_FOUND", "errors": {}},
            status=404
        )

    @api.exception_handler(ObjectDoesNotExist)
    def handle_object_not_exist(request, exc: ObjectDoesNotExist):
        logger.info(f"Object not found: {request.path}")
        return api.create_response(
            request,
            {"error": "资源不存在", "code": "NOT_FOUND", "errors": {}},
            status=404
        )

    @api.exception_handler(DjangoPermissionDenied)
    def handle_django_permission_denied(request, exc: DjangoPermissionDenied):
        logger.warning(f"Permission denied: {request.path}", extra={"user": getattr(request, "user", None)})
        return api.create_response(
            request,
            {"error": "无权限访问", "code": "PERMISSION_DENIED", "errors": {}},
            status=403
        )

    @api.exception_handler(ValidationError)
    def handle_ninja_validation_error(request, exc: ValidationError):
        logger.info(f"Validation error: {request.path}", extra={"errors": exc.errors})
        return api.create_response(
            request,
            {"error": "数据校验失败", "code": "VALIDATION_ERROR", "errors": exc.errors},
            status=422
        )

    @api.exception_handler(HttpError)
    def handle_http_error(request, exc: HttpError):
        logger.warning(f"HTTP Error {exc.status_code}: {request.path}")
        return api.create_response(
            request,
            {"error": str(exc.message), "code": "HTTP_ERROR", "errors": {}},
            status=exc.status_code
        )

    # 11. 未预期的异常 - 500
    @api.exception_handler(Exception)
    def handle_unexpected_exception(request, exc: Exception):
        """处理未预期的异常"""
        logger.error(
            f"未预期的异常: {exc}",
            exc_info=True,
            extra={
                "path": request.path,
                "method": request.method,
                "user_id": getattr(request.auth, 'id', None) if hasattr(request, 'auth') else None
            }
        )
        # 生产环境不暴露详细错误信息
        from django.conf import settings
        message = str(exc) if settings.DEBUG else "系统错误，请稍后重试"
        return api.create_response(
            request,
            {
                "error": message,
                "code": "INTERNAL_ERROR",
                "errors": {}
            },
            status=500
        )
