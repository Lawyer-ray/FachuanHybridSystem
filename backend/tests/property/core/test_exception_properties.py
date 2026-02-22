"""
异常消息中文一致性属性测试

# Feature: backend-quality-to-10, Property 7: 异常消息中文一致性
Validates: Requirements 4.4
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ValidationException,
)
from apps.core.exceptions import (
    BusinessException,
    ExternalServiceError,
    RateLimitError,
)

# 只包含中文字符、数字、中文标点的正则（允许空格）
_CHINESE_ONLY = re.compile(r"^[^\x00-\x7F\u0080-\u00FF\u0100-\u024F]*$")
# 检测英文单词（连续 2 个以上 ASCII 字母）
_ENGLISH_WORD = re.compile(r"[a-zA-Z]{2,}")

# 所有需要验证的异常类及其无参默认消息
_EXCEPTION_CLASSES: list[type[BusinessException]] = [
    ValidationException,
    PermissionDenied,
    NotFoundError,
    ConflictError,
    AuthenticationError,
    RateLimitError,
    ExternalServiceError,
]


class TestExceptionMessageChineseConsistencyProperty:
    """
    Property 7: 异常消息中文一致性

    # Feature: backend-quality-to-10, Property 7: 异常消息中文一致性
    Validates: Requirements 4.4
    """

    @given(st.sampled_from(_EXCEPTION_CLASSES))
    @settings(max_examples=100)
    def test_default_message_contains_no_english_words(
        self, exc_class: type[BusinessException]
    ) -> None:
        """
        Property 7: 无参构造时，默认消息不应包含英文单词。

        # Feature: backend-quality-to-10, Property 7: 异常消息中文一致性
        Validates: Requirements 4.4
        """
        exc = exc_class()  # type: ignore[call-arg]
        msg = exc.message
        assert not _ENGLISH_WORD.search(msg), (  # type: ignore[arg-type]
            f"{exc_class.__name__} 的默认消息包含英文单词: {msg!r}"
        )

    @pytest.mark.parametrize("exc_class", _EXCEPTION_CLASSES)
    def test_each_exception_default_message_is_chinese(
        self, exc_class: type[BusinessException]
    ) -> None:
        """具体验证每个异常类的默认消息为中文。"""
        exc = exc_class()  # type: ignore[call-arg]
        assert exc.message, f"{exc_class.__name__} 默认消息不能为空"
        assert not _ENGLISH_WORD.search(exc.message), (  # type: ignore[arg-type]
            f"{exc_class.__name__} 默认消息含英文: {exc.message!r}"
        )
