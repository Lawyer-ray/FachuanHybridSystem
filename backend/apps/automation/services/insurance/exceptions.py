"""
财产保全询价功能的自定义异常类

提供清晰的错误分类和错误信息，便于错误处理和调试。
"""

from typing import Any

from django.http import status as http_status

from apps.core.exceptions import BusinessError


class PreservationQuoteError(BusinessError):
    """
    询价错误基类

    所有询价相关的错误都应该继承此类。
    """

    def __init__(self, message: str, code: str = "PRESERVATION_QUOTE_ERROR", status: int = http_status.HTTP_400_BAD_REQUEST):
        super().__init__(message=message, code=code, status=status)


class TokenError(PreservationQuoteError):
    """
    Token 相关错误

    当 Token 不存在、已过期或无效时抛出此异常。
    """

    def __init__(self, message: str):
        super().__init__(message=message, code="TOKEN_ERROR", status=http_status.HTTP_401_UNAUTHORIZED)  # Unauthorized


class APIError(PreservationQuoteError):
    """
    API 调用错误

    当调用外部 API 失败时抛出此异常。
    """

    def __init__(self, message: str, status_code: int | None = None):
        code = "API_ERROR"
        if status_code:
            code = f"API_ERROR_{status_code}"

        super().__init__(message=message, code=code, status=http_status.HTTP_502_BAD_GATEWAY)  # Bad Gateway


class NetworkError(PreservationQuoteError):
    """
    网络错误

    当网络请求超时或连接失败时抛出此异常。
    """

    def __init__(self, message: str):
        super().__init__(message=message, code="NETWORK_ERROR", status=http_status.HTTP_504_GATEWAY_TIMEOUT)  # Gateway Timeout


class ValidationError(PreservationQuoteError):
    """
    数据验证错误

    当输入数据不符合要求时抛出此异常。
    """

    def __init__(self, message: str, errors: dict[str, Any] | None = None):
        super().__init__(message=message, code="VALIDATION_ERROR", status=http_status.HTTP_400_BAD_REQUEST)  # Bad Request
        self.errors = errors or {}


class CompanyListEmptyError(PreservationQuoteError):
    """
    保险公司列表为空错误

    当无法获取保险公司列表或列表为空时抛出此异常。
    """

    def __init__(self, message: str = "未获取到保险公司列表"):
        super().__init__(message=message, code="COMPANY_LIST_EMPTY", status=http_status.HTTP_404_NOT_FOUND)  # Not Found


class QuoteExecutionError(PreservationQuoteError):
    """
    询价执行错误

    当询价任务执行过程中发生错误时抛出此异常。
    """

    def __init__(self, message: str, quote_id: int | None = None):
        super().__init__(message=message, code="QUOTE_EXECUTION_ERROR", status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)  # Internal Server Error
        self.quote_id = quote_id


class RetryLimitExceededError(PreservationQuoteError):
    """
    重试次数超限错误

    当任务重试次数超过最大限制时抛出此异常。
    """

    def __init__(self, message: str, max_retries: int | None = None):
        super().__init__(message=message, code="RETRY_LIMIT_EXCEEDED", status=http_status.HTTP_429_TOO_MANY_REQUESTS)  # Too Many Requests
        self.max_retries = max_retries
