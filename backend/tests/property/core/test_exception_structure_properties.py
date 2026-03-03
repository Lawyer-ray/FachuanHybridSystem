"""
Property-Based Tests for Exception Structure

Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
Validates: Requirements 5.4

测试所有 BusinessException 实例包含 message、code、errors 属性，
并且 errors 属性是字典类型。
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from apps.core.exceptions import (
    APIError,
    AuthenticationError,
    BusinessException,
    ConflictError,
    ExternalServiceError,
    NetworkError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
    TokenError,
    ValidationException,
)

# 定义所有 BusinessException 子类
ALL_EXCEPTION_CLASSES = [
    BusinessException,
    ValidationException,
    PermissionDenied,
    NotFoundError,
    ConflictError,
    AuthenticationError,
    RateLimitError,
    ExternalServiceError,
    TokenError,
    APIError,
    NetworkError,
]


# 策略：生成错误消息
error_message_strategy = st.text(min_size=1, max_size=200)

# 策略：生成错误码
error_code_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Nd"), whitelist_characters="_"), min_size=1, max_size=50
    ),
)

# 策略：生成错误详情字典
error_details_strategy = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.text(min_size=1, max_size=50),
        values=st.one_of(
            st.text(max_size=200),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.lists(st.text(max_size=100), max_size=5),
        ),
        max_size=10,
    ),
)


class TestExceptionStructureProperties:
    """测试异常结构的属性"""

    @given(
        exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES),
        message=error_message_strategy,
        code=error_code_strategy,
        errors=error_details_strategy,
    )
    def test_exception_has_required_attributes(self, exception_class, message, code, errors):
        """
        Property 4: 异常包含结构化错误信息

        测试所有 BusinessException 实例包含 message、code、errors 属性

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例
        if code is not None and errors is not None:
            exc = exception_class(message=message, code=code, errors=errors)
        elif code is not None:
            exc = exception_class(message=message, code=code)
        elif errors is not None:
            exc = exception_class(message=message, errors=errors)
        else:
            exc = exception_class(message=message)

        # 验证属性存在
        assert hasattr(exc, "message"), f"{exception_class.__name__} 缺少 message 属性"
        assert hasattr(exc, "code"), f"{exception_class.__name__} 缺少 code 属性"
        assert hasattr(exc, "errors"), f"{exception_class.__name__} 缺少 errors 属性"

        # 验证属性类型
        assert isinstance(exc.message, str), f"{exception_class.__name__}.message 不是字符串类型"
        assert isinstance(exc.code, str), f"{exception_class.__name__}.code 不是字符串类型"
        assert isinstance(exc.errors, dict), f"{exception_class.__name__}.errors 不是字典类型"

        # 验证属性值
        assert exc.message == message, f"{exception_class.__name__}.message 值不正确"

        if code is not None:
            assert exc.code == code, f"{exception_class.__name__}.code 值不正确"
        else:
            # 如果没有提供 code，应该使用默认值
            assert exc.code is not None and len(exc.code) > 0, f"{exception_class.__name__}.code 应该有默认值"

        if errors is not None:
            assert exc.errors == errors, f"{exception_class.__name__}.errors 值不正确"
        else:
            # 如果没有提供 errors，应该是空字典
            assert exc.errors == {}, f"{exception_class.__name__}.errors 应该是空字典"

    @given(exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES), message=error_message_strategy)
    def test_exception_errors_is_always_dict(self, exception_class, message):
        """
        Property 4: errors 属性始终是字典类型

        测试即使不提供 errors 参数，errors 属性也应该是字典类型（空字典）

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例（不提供 errors 参数）
        exc = exception_class(message=message)

        # 验证 errors 是字典类型
        assert isinstance(
            exc.errors, dict
        ), f"{exception_class.__name__}.errors 应该是字典类型，实际是 {type(exc.errors)}"

        # 验证 errors 是空字典
        assert exc.errors == {}, f"{exception_class.__name__}.errors 应该是空字典，实际是 {exc.errors}"

    @given(
        exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES),
        message=error_message_strategy,
        errors=st.dictionaries(
            keys=st.text(min_size=1, max_size=50), values=st.text(max_size=200), min_size=1, max_size=10
        ),
    )
    def test_exception_to_dict_structure(self, exception_class, message, errors):
        """
        Property 4: to_dict() 返回包含 error、code、errors 字段的字典

        测试 to_dict() 方法返回的字典包含必需的字段

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例
        exc = exception_class(message=message, errors=errors)

        # 调用 to_dict()
        result = exc.to_dict()

        # 验证返回值是字典
        assert isinstance(result, dict), f"{exception_class.__name__}.to_dict() 应该返回字典类型"

        # 验证包含必需的字段
        assert "error" in result, f"{exception_class.__name__}.to_dict() 应该包含 'error' 字段"
        assert "code" in result, f"{exception_class.__name__}.to_dict() 应该包含 'code' 字段"
        assert "errors" in result, f"{exception_class.__name__}.to_dict() 应该包含 'errors' 字段"

        # 验证字段类型
        assert isinstance(result["error"], str), f"{exception_class.__name__}.to_dict()['error'] 应该是字符串类型"
        assert isinstance(result["code"], str), f"{exception_class.__name__}.to_dict()['code'] 应该是字符串类型"
        assert isinstance(result["errors"], dict), f"{exception_class.__name__}.to_dict()['errors'] 应该是字典类型"

        # 验证字段值
        assert result["error"] == message, f"{exception_class.__name__}.to_dict()['error'] 值不正确"
        assert result["errors"] == errors, f"{exception_class.__name__}.to_dict()['errors'] 值不正确"

    @given(
        exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES),
        message=error_message_strategy,
        code=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd"), whitelist_characters="_"), min_size=1, max_size=50
        ),
    )
    def test_exception_code_is_string(self, exception_class, message, code):
        """
        Property 4: code 属性始终是字符串类型

        测试 code 属性始终是非空字符串

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例
        exc = exception_class(message=message, code=code)

        # 验证 code 是字符串类型
        assert isinstance(exc.code, str), f"{exception_class.__name__}.code 应该是字符串类型，实际是 {type(exc.code)}"

        # 验证 code 非空
        assert len(exc.code) > 0, f"{exception_class.__name__}.code 不应该是空字符串"

        # 验证 code 值正确
        assert exc.code == code, f"{exception_class.__name__}.code 值不正确"

    @given(exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES), message=error_message_strategy)
    def test_exception_has_default_code(self, exception_class, message):
        """
        Property 4: 异常有默认的 code 值

        测试当不提供 code 参数时，异常应该有默认的 code 值

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例（不提供 code 参数）
        exc = exception_class(message=message)

        # 验证 code 存在且非空
        assert hasattr(exc, "code"), f"{exception_class.__name__} 应该有 code 属性"
        assert isinstance(exc.code, str), f"{exception_class.__name__}.code 应该是字符串类型"
        assert len(exc.code) > 0, f"{exception_class.__name__}.code 不应该是空字符串"

    @given(
        exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES),
        message=error_message_strategy,
        errors=st.dictionaries(
            keys=st.text(min_size=1, max_size=50),
            values=st.one_of(
                st.text(max_size=200),
                st.integers(),
                st.lists(st.text(max_size=100), max_size=5),
                st.dictionaries(keys=st.text(min_size=1, max_size=20), values=st.text(max_size=100), max_size=3),
            ),
            min_size=0,
            max_size=10,
        ),
    )
    def test_exception_errors_preserves_structure(self, exception_class, message, errors):
        """
        Property 4: errors 字典保持结构

        测试 errors 字典的结构在创建和访问时保持不变

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例
        exc = exception_class(message=message, errors=errors)

        # 验证 errors 结构保持不变
        assert exc.errors == errors, f"{exception_class.__name__}.errors 结构应该保持不变"

        # 验证 to_dict() 中的 errors 也保持不变
        result = exc.to_dict()
        assert result["errors"] == errors, f"{exception_class.__name__}.to_dict()['errors'] 结构应该保持不变"

    @given(
        exception_class=st.sampled_from(ALL_EXCEPTION_CLASSES),
        message=error_message_strategy,
        code=error_code_strategy,
        errors=error_details_strategy,
    )
    def test_exception_inheritance(self, exception_class, message, code, errors):
        """
        Property 4: 所有异常都继承自 BusinessException

        测试所有异常类都继承自 BusinessException 和 Exception

        Feature: backend-architecture-refactoring, Property 4: 异常包含结构化错误信息
        Validates: Requirements 5.4
        """
        # 创建异常实例
        if code is not None and errors is not None:
            exc = exception_class(message=message, code=code, errors=errors)
        elif code is not None:
            exc = exception_class(message=message, code=code)
        elif errors is not None:
            exc = exception_class(message=message, errors=errors)
        else:
            exc = exception_class(message=message)

        # 验证继承关系
        assert isinstance(exc, BusinessException), f"{exception_class.__name__} 应该继承自 BusinessException"
        assert isinstance(exc, Exception), f"{exception_class.__name__} 应该继承自 Exception"
