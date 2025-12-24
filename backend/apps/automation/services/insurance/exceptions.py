"""
财产保全询价功能的自定义异常类

提供清晰的错误分类和错误信息，便于错误处理和调试。
"""
from apps.core.exceptions import BusinessError


class PreservationQuoteError(BusinessError):
    """
    询价错误基类
    
    所有询价相关的错误都应该继承此类。
    """
    def __init__(self, message: str, code: str = "PRESERVATION_QUOTE_ERROR", status: int = 400):
        super().__init__(message=message, code=code, status=status)


class TokenError(PreservationQuoteError):
    """
    Token 相关错误
    
    当 Token 不存在、已过期或无效时抛出此异常。
    """
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="TOKEN_ERROR",
            status=401  # Unauthorized
        )


class APIError(PreservationQuoteError):
    """
    API 调用错误
    
    当调用外部 API 失败时抛出此异常。
    """
    def __init__(self, message: str, status_code: int = None):
        code = "API_ERROR"
        if status_code:
            code = f"API_ERROR_{status_code}"
        
        super().__init__(
            message=message,
            code=code,
            status=502  # Bad Gateway
        )


class NetworkError(PreservationQuoteError):
    """
    网络错误
    
    当网络请求超时或连接失败时抛出此异常。
    """
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="NETWORK_ERROR",
            status=504  # Gateway Timeout
        )


class ValidationError(PreservationQuoteError):
    """
    数据验证错误
    
    当输入数据不符合要求时抛出此异常。
    """
    def __init__(self, message: str, errors: dict = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status=400  # Bad Request
        )
        self.errors = errors or {}


class CompanyListEmptyError(PreservationQuoteError):
    """
    保险公司列表为空错误
    
    当无法获取保险公司列表或列表为空时抛出此异常。
    """
    def __init__(self, message: str = "未获取到保险公司列表"):
        super().__init__(
            message=message,
            code="COMPANY_LIST_EMPTY",
            status=404  # Not Found
        )


class QuoteExecutionError(PreservationQuoteError):
    """
    询价执行错误
    
    当询价任务执行过程中发生错误时抛出此异常。
    """
    def __init__(self, message: str, quote_id: int = None):
        super().__init__(
            message=message,
            code="QUOTE_EXECUTION_ERROR",
            status=500  # Internal Server Error
        )
        self.quote_id = quote_id


class RetryLimitExceededError(PreservationQuoteError):
    """
    重试次数超限错误
    
    当任务重试次数超过最大限制时抛出此异常。
    """
    def __init__(self, message: str, max_retries: int = None):
        super().__init__(
            message=message,
            code="RETRY_LIMIT_EXCEEDED",
            status=429  # Too Many Requests
        )
        self.max_retries = max_retries
