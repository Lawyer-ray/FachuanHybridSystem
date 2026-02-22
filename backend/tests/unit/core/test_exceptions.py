"""
测试异常类
"""

import pytest

from apps.core.exceptions import (
    APIError,
    AuthenticationError,
    AutoTokenAcquisitionError,
    BusinessException,
    CaptchaRecognitionError,
    ConflictError,
    ExternalServiceError,
    LoginFailedError,
    NetworkError,
    NoAvailableAccountError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    TokenError,
    ValidationException,
)


class TestBusinessException:
    """测试 BusinessException 基类"""

    def test_create_with_message_only(self):
        """测试只使用 message 创建异常"""
        exc = BusinessException("测试错误")

        assert exc.message == "测试错误"
        assert exc.code == "BusinessException"  # 默认使用类名
        assert exc.errors == {}

    def test_create_with_all_parameters(self):
        """测试使用所有参数创建异常"""
        errors = {"field1": "错误1", "field2": "错误2"}
        exc = BusinessException(message="测试错误", code="TEST_ERROR", errors=errors)

        assert exc.message == "测试错误"
        assert exc.code == "TEST_ERROR"
        assert exc.errors == errors

    def test_str_representation(self):
        """测试字符串表示"""
        exc = BusinessException("测试错误", code="TEST_ERROR")

        assert str(exc) == "TEST_ERROR: 测试错误"

    def test_repr_representation(self):
        """测试详细字符串表示"""
        exc = BusinessException("测试错误", code="TEST_ERROR")

        repr_str = repr(exc)
        assert "BusinessException" in repr_str
        assert "测试错误" in repr_str
        assert "TEST_ERROR" in repr_str

    def test_to_dict(self):
        """测试转换为字典"""
        errors = {"field1": "错误1"}
        exc = BusinessException(message="测试错误", code="TEST_ERROR", errors=errors)
        result = exc.to_dict()
        assert result["error"] == "测试错误"
        assert result["code"] == "TEST_ERROR"
        assert result["errors"] == errors

    def test_to_dict_without_errors(self):
        """测试转换为字典（无 errors）"""
        exc = BusinessException("测试错误", code="TEST_ERROR")
        result = exc.to_dict()
        assert result["error"] == "测试错误"
        assert result["code"] == "TEST_ERROR"
        assert result["errors"] == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = BusinessException("测试错误")

        assert isinstance(exc, Exception)
        assert isinstance(exc, BusinessException)


class TestValidationException:
    """测试 ValidationException"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = ValidationException()

        assert exc.message == "数据验证失败"
        assert exc.code == "VALIDATION_ERROR"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = ValidationException("字段验证失败")

        assert exc.message == "字段验证失败"
        assert exc.code == "VALIDATION_ERROR"

    def test_create_with_errors(self):
        """测试使用错误详情创建"""
        errors = {"name": "名称不能为空", "age": "年龄必须大于0"}
        exc = ValidationException("验证失败", errors=errors)

        assert exc.message == "验证失败"
        assert exc.errors == errors

    def test_inheritance(self):
        """测试继承关系"""
        exc = ValidationException()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, ValidationException)


class TestPermissionDenied:
    """测试 PermissionDenied"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = PermissionDenied()

        assert exc.message == "无权限执行该操作"
        assert exc.code == "PERMISSION_DENIED"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = PermissionDenied("无权限访问该资源")

        assert exc.message == "无权限访问该资源"
        assert exc.code == "PERMISSION_DENIED"

    def test_inheritance(self):
        """测试继承关系"""
        exc = PermissionDenied()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, PermissionDenied)


class TestNotFoundError:
    """测试 NotFoundError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = NotFoundError()

        assert exc.message == "资源不存在"
        assert exc.code == "NOT_FOUND"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = NotFoundError("用户不存在")

        assert exc.message == "用户不存在"
        assert exc.code == "NOT_FOUND"

    def test_inheritance(self):
        """测试继承关系"""
        exc = NotFoundError()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, NotFoundError)


class TestConflictError:
    """测试 ConflictError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = ConflictError()

        assert exc.message == "资源冲突"
        assert exc.code == "CONFLICT"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = ConflictError("用户名已存在")

        assert exc.message == "用户名已存在"
        assert exc.code == "CONFLICT"

    def test_inheritance(self):
        """测试继承关系"""
        exc = ConflictError()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, ConflictError)


class TestAuthenticationError:
    """测试 AuthenticationError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = AuthenticationError()

        assert exc.message == "认证失败"
        assert exc.code == "AUTHENTICATION_ERROR"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = AuthenticationError("Token 已过期")

        assert exc.message == "Token 已过期"
        assert exc.code == "AUTHENTICATION_ERROR"

    def test_inheritance(self):
        """测试继承关系"""
        exc = AuthenticationError()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, AuthenticationError)


class TestRateLimitError:
    """测试 RateLimitError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = RateLimitError()

        assert exc.message == "请求过于频繁"
        assert exc.code == "RATE_LIMIT_ERROR"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = RateLimitError("超过每日配额")

        assert exc.message == "超过每日配额"
        assert exc.code == "RATE_LIMIT_ERROR"

    def test_inheritance(self):
        """测试继承关系"""
        exc = RateLimitError()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, RateLimitError)


class TestExternalServiceError:
    """测试 ExternalServiceError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = ExternalServiceError()

        assert exc.message == "外部服务错误"
        assert exc.code == "EXTERNAL_SERVICE_ERROR"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = ExternalServiceError("第三方 API 调用失败")

        assert exc.message == "第三方 API 调用失败"
        assert exc.code == "EXTERNAL_SERVICE_ERROR"

    def test_inheritance(self):
        """测试继承关系"""
        exc = ExternalServiceError()

        assert isinstance(exc, BusinessException)
        assert isinstance(exc, ExternalServiceError)


class TestServiceUnavailableError:
    """测试 ServiceUnavailableError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = ServiceUnavailableError()

        assert exc.message == "服务暂时不可用"
        assert exc.code == "SERVICE_UNAVAILABLE"
        assert exc.errors == {}
        assert exc.service_name is None

    def test_create_with_service_name(self):
        """测试使用服务名创建"""
        exc = ServiceUnavailableError(service_name="ollama")

        assert exc.message == "服务暂时不可用"
        assert exc.service_name == "ollama"
        assert exc.errors["service"] == "ollama"

    def test_inheritance(self):
        """测试继承关系"""
        exc = ServiceUnavailableError()

        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestRecognitionTimeoutError:
    """测试 RecognitionTimeoutError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = RecognitionTimeoutError()

        assert exc.message == "识别超时"
        assert exc.code == "RECOGNITION_TIMEOUT"
        assert exc.errors == {}
        assert exc.timeout_seconds is None

    def test_create_with_timeout_seconds(self):
        """测试使用超时时间创建"""
        exc = RecognitionTimeoutError(timeout_seconds=30.0)

        assert exc.message == "识别超时"
        assert exc.timeout_seconds == 30.0
        assert exc.errors["timeout_seconds"] == 30.0

    def test_inheritance(self):
        """测试继承关系"""
        exc = RecognitionTimeoutError()

        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestTokenError:
    """测试 TokenError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = TokenError()

        assert exc.message == "Token 错误"
        assert exc.code == "TOKEN_ERROR"
        assert exc.errors == {}

    def test_create_with_custom_message(self):
        """测试使用自定义消息创建"""
        exc = TokenError("Token 已过期")

        assert exc.message == "Token 已过期"
        assert exc.code == "TOKEN_ERROR"

    def test_inheritance(self):
        """测试继承关系"""
        exc = TokenError()

        assert isinstance(exc, BusinessException)


class TestAPIError:
    """测试 APIError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = APIError()

        assert exc.message == "API 调用错误"
        assert exc.code == "API_ERROR"
        assert exc.errors == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = APIError()

        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestNetworkError:
    """测试 NetworkError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = NetworkError()

        assert exc.message == "网络错误"
        assert exc.code == "NETWORK_ERROR"
        assert exc.errors == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = NetworkError()

        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestAutoTokenAcquisitionError:
    """测试 AutoTokenAcquisitionError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = AutoTokenAcquisitionError()

        assert exc.message == "自动Token获取失败"
        assert exc.code == "AUTO_TOKEN_ACQUISITION_ERROR"
        assert exc.errors == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = AutoTokenAcquisitionError()

        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestLoginFailedError:
    """测试 LoginFailedError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = LoginFailedError()

        assert exc.message == "登录失败"
        assert exc.code == "LOGIN_FAILED"
        assert exc.errors == {}
        assert exc.attempts == []

    def test_create_with_attempts(self):
        """测试使用尝试记录创建"""
        attempts = [{"account": "test", "result": "failed"}]
        exc = LoginFailedError(attempts=attempts)

        assert exc.attempts == attempts

    def test_inheritance(self):
        """测试继承关系"""
        exc = LoginFailedError()

        assert isinstance(exc, AutoTokenAcquisitionError)
        assert isinstance(exc, ExternalServiceError)
        assert isinstance(exc, BusinessException)


class TestNoAvailableAccountError:
    """测试 NoAvailableAccountError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = NoAvailableAccountError()

        assert exc.message == "无可用账号"
        assert exc.code == "NO_AVAILABLE_ACCOUNT"
        assert exc.errors == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = NoAvailableAccountError()

        assert isinstance(exc, AutoTokenAcquisitionError)


class TestCaptchaRecognitionError:
    """测试 CaptchaRecognitionError"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        exc = CaptchaRecognitionError()

        assert exc.message == "验证码识别失败"
        assert exc.code == "CAPTCHA_RECOGNITION_ERROR"
        assert exc.errors == {}

    def test_inheritance(self):
        """测试继承关系"""
        exc = CaptchaRecognitionError()

        assert isinstance(exc, ExternalServiceError)


class TestExceptionHierarchy:
    """测试异常继承层次"""

    def test_all_exceptions_inherit_from_business_exception(self):
        """测试所有异常都继承自 BusinessException"""
        exceptions = [
            ValidationException(),
            PermissionDenied(),
            NotFoundError(),
            ConflictError(),
            AuthenticationError(),
            RateLimitError(),
            ExternalServiceError(),
            ServiceUnavailableError(),
            RecognitionTimeoutError(),
            TokenError(),
            APIError(),
            NetworkError(),
            AutoTokenAcquisitionError(),
            LoginFailedError(),
            NoAvailableAccountError(),
            CaptchaRecognitionError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, BusinessException)
            assert isinstance(exc, Exception)

    def test_exception_codes_are_unique(self):
        """测试异常码是唯一的"""
        exceptions = [
            ValidationException(),
            PermissionDenied(),
            NotFoundError(),
            ConflictError(),
            AuthenticationError(),
            RateLimitError(),
            ExternalServiceError(),
            ServiceUnavailableError(),
            RecognitionTimeoutError(),
            TokenError(),
            APIError(),
            NetworkError(),
            AutoTokenAcquisitionError(),
            LoginFailedError(),
            NoAvailableAccountError(),
            CaptchaRecognitionError(),
        ]

        codes = [exc.code for exc in exceptions]
        assert len(codes) == len(set(codes))  # 所有 code 都是唯一的

    def test_to_dict_consistency(self):
        """测试所有异常的 to_dict 方法返回一致的结构"""
        exceptions = [
            ValidationException(),
            PermissionDenied(),
            NotFoundError(),
            ConflictError(),
            AuthenticationError(),
            RateLimitError(),
            ExternalServiceError(),
        ]

        for exc in exceptions:
            result = exc.to_dict()
            # 验证必需字段存在
            assert "error" in result
            assert "code" in result
            assert "errors" in result
            # 验证字段类型
            assert isinstance(result["error"], str)
            assert isinstance(result["code"], str)
            assert isinstance(result["errors"], dict)
