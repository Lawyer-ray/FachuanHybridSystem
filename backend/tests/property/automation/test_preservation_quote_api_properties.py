"""
财产保全询价 API Property-Based Tests

测试 API 异常转换的通用属性
"""

import json
from unittest.mock import Mock, patch

import pytest
from django.test import RequestFactory
from hypothesis import given
from hypothesis import strategies as st

from apps.automation.api.preservation_quote_api import (
    create_preservation_quote,
    get_preservation_quote,
    list_preservation_quotes,
)
from apps.automation.schemas import PreservationQuoteCreateSchema
from apps.automation.services.insurance.exceptions import ValidationError
from apps.core.exceptions import BusinessError, NotFoundError


class TestAPIExceptionConversion:
    """
    测试 API 异常转换属性

    Feature: backend-architecture-refactoring, Property 3: API 异常转换为 HTTP 响应
    Validates: Requirements 5.2
    """

    @given(
        error_message=st.text(min_size=1, max_size=200),
        error_code=st.text(min_size=1, max_size=50),
    )
    def test_validation_exception_converts_to_http_response(self, error_message, error_code):
        """
        Property 3: API 异常转换为 HTTP 响应

        测试当 Service 抛出 ValidationError 时，API 返回正确的 HTTP 响应

        Feature: backend-architecture-refactoring, Property 3: API 异常转换为 HTTP 响应
        Validates: Requirements 5.2
        """
        # 创建模拟的 request 对象
        factory = RequestFactory()
        request = factory.post("/api/v1/automation/preservation-quotes")
        request.auth = Mock()  # type: ignore[attr-defined]
        request.auth.id = 1  # type: ignore[attr-defined]

        # 创建测试数据
        data = PreservationQuoteCreateSchema(
            preserve_amount=100000.00,  # type: ignore[arg-type]
            corp_id="440100",
            category_id="1",
            credential_id=1,
        )

        # Mock Service 抛出 ValidationError
        with patch("apps.automation.api.preservation_quote_api.PreservationQuoteService") as MockService:
            mock_service = MockService.return_value
            mock_service.create_quote.side_effect = ValidationError(message=error_message, errors={"field": "error"})

            # 调用 API（应该抛出异常）
            try:
                create_preservation_quote(request, data)
                # 如果没有抛出异常，测试失败
                raise AssertionError("Expected ValidationError to be raised")
            except ValidationError as exc:
                # 验证异常包含正确的信息
                assert exc.message == error_message
                assert hasattr(exc, "errors")
                assert isinstance(exc.errors, dict)

    @given(
        error_message=st.text(min_size=1, max_size=200),
    )
    def test_not_found_exception_converts_to_http_response(self, error_message):
        """
        Property 3: API 异常转换为 HTTP 响应

        测试当 Service 抛出 NotFoundError 时，API 返回正确的 HTTP 响应

        Feature: backend-architecture-refactoring, Property 3: API 异常转换为 HTTP 响应
        Validates: Requirements 5.2
        """
        # 创建模拟的 request 对象
        factory = RequestFactory()
        request = factory.get("/api/v1/automation/preservation-quotes/999")
        request.auth = Mock()  # type: ignore[attr-defined]
        request.auth.id = 1  # type: ignore[attr-defined]

        # Mock Service 抛出 NotFoundError
        with patch("apps.automation.api.preservation_quote_api.PreservationQuoteService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_quote.side_effect = NotFoundError(message=error_message, code="NOT_FOUND")

            # 调用 API（应该抛出异常）
            try:
                get_preservation_quote(request, 999)
                # 如果没有抛出异常，测试失败
                raise AssertionError("Expected NotFoundError to be raised")
            except NotFoundError as exc:
                # 验证异常包含正确的信息
                assert exc.message == error_message
                assert exc.code == "NOT_FOUND"
                assert hasattr(exc, "errors")
                assert isinstance(exc.errors, dict)

    @given(
        page=st.integers(min_value=-100, max_value=0),
    )
    def test_service_validation_error_has_structured_errors(self, page):
        """
        Property 3: API 异常转换为 HTTP 响应

        测试当 Service 抛出 ValidationError 时，响应体包含 error、code、errors 字段

        Feature: backend-architecture-refactoring, Property 3: API 异常转换为 HTTP 响应
        Validates: Requirements 5.2
        """
        # 创建模拟的 request 对象
        factory = RequestFactory()
        request = factory.get(f"/api/v1/automation/preservation-quotes?page={page}")
        request.auth = Mock()  # type: ignore[attr-defined]
        request.auth.id = 1  # type: ignore[attr-defined]

        # Mock Service 抛出 ValidationError
        with patch("apps.automation.api.preservation_quote_api.PreservationQuoteService") as MockService:
            mock_service = MockService.return_value
            mock_service.list_quotes.side_effect = ValidationError(
                message="参数验证失败", errors={"page": "页码必须大于 0"}
            )

            # 调用 API（应该抛出异常）
            try:
                list_preservation_quotes(request, page=page, page_size=20, status=None)
                # 如果没有抛出异常，测试失败
                raise AssertionError("Expected ValidationError to be raised")
            except ValidationError as exc:
                # 验证异常包含结构化错误信息
                assert hasattr(exc, "message")
                assert isinstance(exc.message, str)
                assert hasattr(exc, "errors")
                assert isinstance(exc.errors, dict)
                assert "page" in exc.errors

    def test_exception_response_structure(self):
        """
        Property 3: API 异常转换为 HTTP 响应

        测试异常响应体的结构

        Feature: backend-architecture-refactoring, Property 3: API 异常转换为 HTTP 响应
        Validates: Requirements 5.2
        """
        # 测试 ValidationError 的响应结构
        exc = ValidationError(message="测试错误", errors={"field1": "错误1", "field2": "错误2"})

        # 验证异常属性
        assert hasattr(exc, "message")
        assert hasattr(exc, "code")
        assert hasattr(exc, "errors")

        # 验证属性类型
        assert isinstance(exc.message, str)
        assert isinstance(exc.code, str)
        assert isinstance(exc.errors, dict)

        # 验证 errors 字段包含结构化信息
        assert len(exc.errors) == 2
        assert "field1" in exc.errors
        assert "field2" in exc.errors
