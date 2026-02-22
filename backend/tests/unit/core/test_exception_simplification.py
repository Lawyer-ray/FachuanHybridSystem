"""
Property 4: 异常合并后 Code 唯一性

**Feature: backend-perfect-score, Property 4: 异常合并后 Code 唯一性**

验证每个 OwnerSettingException 的 code 字段唯一标识错误类型，
且与原异常类的语义一致。

**Validates: Requirements 5.2**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.exceptions import (
    OwnerSettingException,
    owner_config_error,
    owner_network_error,
    owner_not_found_error,
    owner_permission_error,
    owner_retry_error,
    owner_timeout_error,
    owner_validation_error,
)

# 所有已知 code → 快捷构造函数的映射
OWNER_CODE_FACTORIES = {
    "OWNER_PERMISSION_ERROR": owner_permission_error,
    "OWNER_NOT_FOUND": owner_not_found_error,
    "OWNER_VALIDATION_ERROR": owner_validation_error,
    "OWNER_RETRY_ERROR": owner_retry_error,
    "OWNER_TIMEOUT_ERROR": owner_timeout_error,
    "OWNER_NETWORK_ERROR": owner_network_error,
    "OWNER_CONFIG_ERROR": owner_config_error,
}


class TestOwnerExceptionCodeUniqueness:
    """单元测试：code 字段唯一性"""

    def test_each_factory_produces_correct_code(self) -> None:
        """每个快捷构造函数产生正确的 code"""
        for expected_code, factory in OWNER_CODE_FACTORIES.items():
            exc = factory()
            assert exc.code == expected_code, f"{factory.__name__} 应产生 code={expected_code}"

    def test_all_codes_are_unique(self) -> None:
        """所有 code 值互不相同"""
        codes = list(OWNER_CODE_FACTORIES.keys())
        assert len(codes) == len(set(codes)), "存在重复的 code 值"

    def test_all_exceptions_are_owner_setting_exception(self) -> None:
        """所有快捷构造函数返回 OwnerSettingException 实例"""
        for factory in OWNER_CODE_FACTORIES.values():
            exc = factory()
            assert isinstance(exc, OwnerSettingException)

    def test_direct_construction_with_code(self) -> None:
        """直接构造时 code 字段被正确设置"""
        exc = OwnerSettingException(message="测试", code="OWNER_PERMISSION_ERROR")
        assert exc.code == "OWNER_PERMISSION_ERROR"

    def test_default_code_when_none(self) -> None:
        """不传 code 时使用默认值"""
        exc = OwnerSettingException(message="测试")
        assert exc.code == "OWNER_SETTING_ERROR"

    def test_factory_custom_message(self) -> None:
        """快捷构造函数支持自定义消息"""
        exc = owner_permission_error(message="自定义权限错误")
        assert exc.message == "自定义权限错误"
        assert exc.code == "OWNER_PERMISSION_ERROR"

    def test_backward_compat_aliases_are_same_class(self) -> None:
        """向后兼容别名指向同一个类"""
        from apps.core.exceptions import (
            OwnerConfigException,
            OwnerNetworkException,
            OwnerNotFoundException,
            OwnerPermissionException,
            OwnerRetryException,
            OwnerTimeoutException,
            OwnerValidationException,
        )

        aliases = [
            OwnerPermissionException,
            OwnerNotFoundException,
            OwnerValidationException,
            OwnerRetryException,
            OwnerTimeoutException,
            OwnerNetworkException,
            OwnerConfigException,
        ]
        for alias in aliases:
            assert alias is OwnerSettingException, f"{alias} 应是 OwnerSettingException 的别名"

    def test_isinstance_check_still_works(self) -> None:
        """isinstance 检查对别名仍然有效"""
        from apps.core.exceptions import OwnerPermissionException

        exc = owner_permission_error()
        assert isinstance(exc, OwnerPermissionException)
        assert isinstance(exc, OwnerSettingException)


# ── Property-Based Tests ──────────────────────────────────────────────────────

code_strategy = st.sampled_from(list(OWNER_CODE_FACTORIES.keys()))
message_strategy = st.text(min_size=1, max_size=200)


@given(code=code_strategy, message=message_strategy)
@settings(max_examples=100)
def test_property_code_uniquely_identifies_error_type(code: str, message: str) -> None:
    """
    **Feature: backend-perfect-score, Property 4: 异常合并后 Code 唯一性**

    对于任意 OwnerSettingException 实例，其 code 字段应唯一标识错误类型，
    且与原异常类的语义一致。

    **Validates: Requirements 5.2**
    """
    exc = OwnerSettingException(message=message, code=code)

    # code 字段被正确保存
    assert exc.code == code

    # 是 OwnerSettingException 实例
    assert isinstance(exc, OwnerSettingException)

    # code 在已知集合中
    assert code in OWNER_CODE_FACTORIES


@given(code=code_strategy, message=message_strategy)
@settings(max_examples=100)
def test_property_factory_code_matches_expected(code: str, message: str) -> None:
    """
    **Feature: backend-perfect-score, Property 4: 异常合并后 Code 唯一性**

    快捷构造函数产生的异常 code 与预期一致，不受 message 影响。

    **Validates: Requirements 5.2**
    """
    factory = OWNER_CODE_FACTORIES[code]
    exc = factory(message=message)

    # code 不受 message 影响
    assert exc.code == code

    # message 被正确保存
    assert exc.message == message


@given(
    code1=code_strategy,
    code2=code_strategy,
    message=message_strategy,
)
@settings(max_examples=100)
def test_property_different_codes_produce_different_semantics(code1: str, code2: str, message: str) -> None:
    """
    **Feature: backend-perfect-score, Property 4: 异常合并后 Code 唯一性**

    不同 code 的异常语义不同（code 是唯一标识符）。

    **Validates: Requirements 5.2**
    """
    exc1 = OwnerSettingException(message=message, code=code1)
    exc2 = OwnerSettingException(message=message, code=code2)

    if code1 == code2:
        assert exc1.code == exc2.code
    else:
        assert exc1.code != exc2.code
