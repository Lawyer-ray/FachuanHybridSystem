"""
测试异常处理器的集成测试
测试 API 层捕获异常并转换为 HTTP 响应
"""

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.test import Client
from ninja import NinjaAPI, Router
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError

from apps.core.exceptions import (
    AuthenticationError,
    BusinessException,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    ValidationException,
)
from apps.core.exceptions import register_exception_handlers
from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError

# 创建测试用的 API 实例
test_api = NinjaAPI()
register_exception_handlers(test_api)

# 创建测试路由
test_router = Router()


@test_router.get("/validation-error")
def raise_validation_error(request):
    """抛出 ValidationException"""
    raise ValidationException(
        message="数据验证失败", code="VALIDATION_ERROR", errors={"field1": "错误1", "field2": "错误2"}
    )


@test_router.get("/permission-denied")
def raise_permission_denied(request):
    """抛出 PermissionDenied"""
    raise PermissionDenied(message="无权限访问该资源", code="PERMISSION_DENIED")


@test_router.get("/not-found")
def raise_not_found(request):
    """抛出 NotFoundError"""
    raise NotFoundError(message="资源不存在", code="NOT_FOUND")


@test_router.get("/conflict")
def raise_conflict(request):
    """抛出 ConflictError"""
    raise ConflictError(message="资源已存在", code="CONFLICT")


@test_router.get("/authentication-error")
def raise_authentication_error(request):
    """抛出 AuthenticationError"""
    raise AuthenticationError(message="Token 已过期", code="AUTHENTICATION_ERROR")


@test_router.get("/rate-limit")
def raise_rate_limit(request):
    """抛出 RateLimitError"""
    raise RateLimitError(message="请求过于频繁", code="RATE_LIMIT_ERROR")


@test_router.get("/external-service-error")
def raise_external_service_error(request):
    """抛出 ExternalServiceError"""
    raise ExternalServiceError(message="第三方 API 调用失败", code="EXTERNAL_SERVICE_ERROR")


@test_router.get("/llm-timeout")
def raise_llm_timeout_error(request):
    raise LLMTimeoutError(message="LLM 请求超时", code="LLM_TIMEOUT", errors={"timeout_seconds": 10})


@test_router.get("/llm-backend-unavailable")
def raise_llm_backend_unavailable_error(request):
    raise LLMBackendUnavailableError(message="所有 LLM 后端均不可用", errors={"attempts": [("a", "x")]})


@test_router.get("/llm-rate-limit")
def raise_llm_rate_limit_error(request):
    raise LLMAPIError(message="LLM 触发限流", code="LLM_API_ERROR", errors={"status_code": 429}, status_code=429)


@test_router.get("/business-exception")
def raise_business_exception(request):
    """抛出通用 BusinessException"""
    raise BusinessException(message="业务错误", code="BUSINESS_ERROR")


# 注册测试路由
test_api.add_router("/test", test_router)


@pytest.fixture
def api_client():
    """创建测试客户端"""
    from django.conf import settings
    from django.urls import path

    # 临时添加测试路由
    if not hasattr(settings, "ROOT_URLCONF"):
        settings.ROOT_URLCONF = "apiSystem.urls"

    # 创建测试客户端
    client = Client()
    return client


class TestExceptionHandlers:
    """测试异常处理器"""

    def test_validation_exception_returns_400(self):
        """测试 ValidationException 返回 400 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/validation-error")

        try:
            raise_validation_error(request)
        except ValidationException as exc:
            response = test_api._exception_handlers[ValidationException](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 400
            assert data["error"] == "数据验证失败"
            assert data["code"] == "VALIDATION_ERROR"
            assert "errors" in data
            assert data["errors"] == {"field1": "错误1", "field2": "错误2"}

    def test_permission_denied_returns_403(self):
        """测试 PermissionDenied 返回 403 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/permission-denied")

        try:
            raise_permission_denied(request)
        except PermissionDenied as exc:
            response = test_api._exception_handlers[PermissionDenied](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 403
            assert data["error"] == "无权限访问该资源"
            assert data["code"] == "PERMISSION_DENIED"
            assert "errors" in data

    def test_not_found_returns_404(self):
        """测试 NotFoundError 返回 404 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/not-found")

        try:
            raise_not_found(request)
        except NotFoundError as exc:
            response = test_api._exception_handlers[NotFoundError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 404
            assert data["error"] == "资源不存在"
            assert data["code"] == "NOT_FOUND"
            assert "errors" in data

    def test_conflict_returns_409(self):
        """测试 ConflictError 返回 409 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/conflict")

        try:
            raise_conflict(request)
        except ConflictError as exc:
            response = test_api._exception_handlers[ConflictError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 409
            assert data["error"] == "资源已存在"
            assert data["code"] == "CONFLICT"
            assert "errors" in data

    def test_authentication_error_returns_401(self):
        """测试 AuthenticationError 返回 401 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/authentication-error")

        try:
            raise_authentication_error(request)
        except AuthenticationError as exc:
            response = test_api._exception_handlers[AuthenticationError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 401
            assert data["error"] == "Token 已过期"
            assert data["code"] == "AUTHENTICATION_ERROR"
            assert "errors" in data

    def test_rate_limit_returns_429(self):
        """测试 RateLimitError 返回 429 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/rate-limit")

        try:
            raise_rate_limit(request)
        except RateLimitError as exc:
            response = test_api._exception_handlers[RateLimitError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 429
            assert data["error"] == "请求过于频繁"
            assert data["code"] == "RATE_LIMIT_ERROR"
            assert "errors" in data

    def test_rate_limit_sets_retry_after_header_when_present(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/rate-limit", HTTP_X_REQUEST_ID="rid-hdr")

        exc = RateLimitError(message="请求过于频繁", code="RATE_LIMIT_ERROR", errors={"retry_after": 7})
        response = test_api._exception_handlers[RateLimitError](request, exc)
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "7"

    def test_http404_object_does_not_exist_and_permission_denied(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/missing", HTTP_X_REQUEST_ID="rid-404")

        response = test_api._exception_handlers[Http404](request, Http404())
        data = json.loads(response.content)
        assert response.status_code == 404
        assert data["code"] == "NOT_FOUND"
        assert data["request_id"] == "rid-404"
        assert data["trace_id"] == "rid-404"

        class _Missing(ObjectDoesNotExist):
            pass

        response = test_api._exception_handlers[ObjectDoesNotExist](request, _Missing())
        data = json.loads(response.content)
        assert response.status_code == 404
        assert data["code"] == "NOT_FOUND"

        response = test_api._exception_handlers[DjangoPermissionDenied](request, DjangoPermissionDenied())
        data = json.loads(response.content)
        assert response.status_code == 403
        assert data["code"] == "PERMISSION_DENIED"

    def test_ninja_validation_error_maps_to_422(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/validation", HTTP_X_REQUEST_ID="rid-422")

        exc = NinjaValidationError(errors=[{"loc": ["query", "x"], "msg": "bad", "type": "value_error"}])
        response = test_api._exception_handlers[NinjaValidationError](request, exc)
        data = json.loads(response.content)

        assert response.status_code == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert data["request_id"] == "rid-422"

    def test_http_error_429_and_non_429(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/http-error", HTTP_X_REQUEST_ID="rid-http")

        response = test_api._exception_handlers[HttpError](request, HttpError(429, "too many"))
        data = json.loads(response.content)
        assert response.status_code == 429
        assert data["code"] == "RATE_LIMIT_ERROR"

        response = test_api._exception_handlers[HttpError](request, HttpError(418, "teapot"))
        data = json.loads(response.content)
        assert response.status_code == 418
        assert data["code"] == "HTTP_ERROR"

    def test_unexpected_exception_hides_message_in_production(self, settings):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/boom", HTTP_X_REQUEST_ID="rid-500")

        settings.DEBUG = True
        response = test_api._exception_handlers[Exception](request, RuntimeError("boom"))
        data = json.loads(response.content)
        assert response.status_code == 500
        assert data["message"] == "boom"

        settings.DEBUG = False
        response = test_api._exception_handlers[Exception](request, RuntimeError("boom"))
        data = json.loads(response.content)
        assert response.status_code == 500
        assert data["message"] != "boom"

    def test_invalid_token_detail_variants(self):
        import json

        from django.test import RequestFactory

        try:
            from ninja_jwt.exceptions import InvalidToken
        except ImportError:
            return

        factory = RequestFactory()
        request = factory.get("/test/token", HTTP_X_REQUEST_ID="rid-token")

        exc = InvalidToken(detail={"detail": "bad token"})
        response = test_api._exception_handlers[InvalidToken](request, exc)
        data = json.loads(response.content)
        assert response.status_code == 401
        assert data["code"] == "INVALID_TOKEN"
        assert data["message"] == "bad token"

        exc = InvalidToken(detail="oops")
        response = test_api._exception_handlers[InvalidToken](request, exc)
        data = json.loads(response.content)
        assert response.status_code == 401
        assert data["code"] == "INVALID_TOKEN"

    def test_llm_exception_handlers(self):
        import json

        from django.test import RequestFactory

        from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError, LLMTimeoutError

        factory = RequestFactory()
        request = factory.get("/test/llm", HTTP_X_REQUEST_ID="rid-llm")

        response = test_api._exception_handlers[LLMBackendUnavailableError](request, LLMBackendUnavailableError())
        data = json.loads(response.content)
        assert response.status_code == 503
        assert data["code"] == "LLM_ALL_BACKENDS_UNAVAILABLE"

        response = test_api._exception_handlers[LLMTimeoutError](request, LLMTimeoutError())
        data = json.loads(response.content)
        assert response.status_code == 504
        assert data["code"] == "LLM_TIMEOUT"

        response = test_api._exception_handlers[LLMAPIError](request, LLMAPIError(status_code=429))
        assert response.status_code == 429

        response = test_api._exception_handlers[LLMAPIError](request, LLMAPIError(status_code=503))
        assert response.status_code == 503

    def test_llm_timeout_returns_504(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/llm-timeout")

        try:
            raise_llm_timeout_error(request)
        except LLMTimeoutError as exc:
            response = test_api._exception_handlers[LLMTimeoutError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 504
            assert data["code"] == "LLM_TIMEOUT"

    def test_llm_backend_unavailable_returns_503(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/llm-backend-unavailable")

        try:
            raise_llm_backend_unavailable_error(request)
        except LLMBackendUnavailableError as exc:
            response = test_api._exception_handlers[LLMBackendUnavailableError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 503
            assert data["code"] == "LLM_ALL_BACKENDS_UNAVAILABLE"

    def test_llm_api_rate_limit_returns_429(self):
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/llm-rate-limit")

        try:
            raise_llm_rate_limit_error(request)
        except LLMAPIError as exc:
            response = test_api._exception_handlers[LLMAPIError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 429
            assert data["code"] == "LLM_API_ERROR"

    def test_external_service_error_returns_502(self):
        """测试 ExternalServiceError 返回 502 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/external-service-error")

        try:
            raise_external_service_error(request)
        except ExternalServiceError as exc:
            response = test_api._exception_handlers[ExternalServiceError](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 502
            assert data["error"] == "第三方 API 调用失败"
            assert data["code"] == "EXTERNAL_SERVICE_ERROR"
            assert "errors" in data

    def test_business_exception_returns_400(self):
        """测试通用 BusinessException 返回 400 状态码"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/business-exception")

        try:
            raise_business_exception(request)
        except BusinessException as exc:
            response = test_api._exception_handlers[BusinessException](request, exc)
            data = json.loads(response.content)

            assert response.status_code == 400
            assert data["error"] == "业务错误"
            assert data["code"] == "BUSINESS_ERROR"
            assert "errors" in data


class TestResponseStructure:
    """测试响应体结构"""

    def test_response_has_required_fields(self):
        """测试响应体包含必需的字段"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/validation-error")

        try:
            raise_validation_error(request)
        except ValidationException as exc:
            response = test_api._exception_handlers[ValidationException](request, exc)
            data = json.loads(response.content)

            # 验证响应体包含 error、code、errors 字段
            assert "error" in data
            assert "code" in data
            assert "errors" in data

            # 验证字段类型
            assert isinstance(data["error"], str)
            assert isinstance(data["code"], str)
            assert isinstance(data["errors"], dict)

    def test_response_errors_field_is_dict(self):
        """测试响应体的 errors 字段是字典类型"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/not-found")

        try:
            raise_not_found(request)
        except NotFoundError as exc:
            response = test_api._exception_handlers[NotFoundError](request, exc)
            data = json.loads(response.content)

            # 即使没有错误详情，errors 也应该是空字典
            assert isinstance(data["errors"], dict)

    def test_response_with_structured_errors(self):
        """测试响应体包含结构化错误信息"""
        import json

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/test/validation-error")

        try:
            raise_validation_error(request)
        except ValidationException as exc:
            response = test_api._exception_handlers[ValidationException](request, exc)
            data = json.loads(response.content)

            # 验证结构化错误信息
            assert data["errors"] == {"field1": "错误1", "field2": "错误2"}


class TestExceptionMapping:
    """测试异常类型与 HTTP 状态码的映射"""

    def test_exception_status_code_mapping(self):
        """测试不同异常类型对应的 HTTP 状态码"""
        from django.test import RequestFactory

        factory = RequestFactory()

        # 定义异常类型和期望的状态码
        exception_mapping = [
            (ValidationException("测试"), 400),
            (AuthenticationError("测试"), 401),
            (PermissionDenied("测试"), 403),
            (NotFoundError("测试"), 404),
            (ConflictError("测试"), 409),
            (RateLimitError("测试"), 429),
            (ExternalServiceError("测试"), 502),
            (BusinessException("测试"), 400),
        ]

        for exc, expected_status in exception_mapping:
            request = factory.get("/test")
            handler = test_api._exception_handlers.get(type(exc))

            if handler:
                response = handler(request, exc)
                assert (
                    response.status_code == expected_status
                ), f"{type(exc).__name__} 应该返回 {expected_status}，实际返回 {response.status_code}"
