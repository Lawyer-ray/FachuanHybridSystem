"""Permission_Mixin Property-Based Tests

# Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
Validates: Requirements 2.7, 2.8

测试 PermissionMixin 在各种 AccessContext 下的异常抛出行为：
1. perm_open_access=False + 未认证用户 → check_authenticated 抛出 AuthenticationError
2. perm_open_access=True → check_authenticated 不抛出任何异常
3. 管理员用户 → check_resource_access 不抛出任何异常（即使 resource_check 返回 False）
4. 已认证普通用户 + resource_check 返回 False → check_resource_access 抛出 PermissionDenied
5. 已认证普通用户 + resource_check 返回 True → check_resource_access 不抛出任何异常
"""

from __future__ import annotations

import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.core.permissions import AccessContext, PermissionMixin
from tests.strategies.permission_strategies import (
    access_context_strategy,
    admin_user_strategy,
    authenticated_user_strategy,
    unauthenticated_user_strategy,
)

logger = logging.getLogger(__name__)

_mixin = PermissionMixin()


class TestPermissionMixinExceptionTypeProperty:
    """
    Property 3: 权限检查异常类型正确性

    # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
    Validates: Requirements 2.7, 2.8
    """

    @given(
        ctx=access_context_strategy(
            user_st=unauthenticated_user_strategy(),
            perm_open_access_st=st.just(False),
        )
    )
    @settings(max_examples=100)
    def test_unauthenticated_closed_access_raises_authentication_error(self, ctx: AccessContext) -> None:
        """
        场景 1：perm_open_access=False + 未认证用户 → check_authenticated 抛出 AuthenticationError。

        # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
        Validates: Requirements 2.8
        """
        with pytest.raises(AuthenticationError):
            _mixin.check_authenticated(ctx)

    @given(
        ctx=access_context_strategy(
            user_st=unauthenticated_user_strategy(),
            perm_open_access_st=st.just(True),
        )
    )
    @settings(max_examples=100)
    def test_open_access_does_not_raise(self, ctx: AccessContext) -> None:
        """
        场景 2：perm_open_access=True → check_authenticated 不抛出任何异常。

        # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
        Validates: Requirements 2.8
        """
        # 不应抛出任何异常
        _mixin.check_authenticated(ctx)

    @given(
        ctx=access_context_strategy(
            user_st=admin_user_strategy(),
            perm_open_access_st=st.booleans(),
        )
    )
    @settings(max_examples=100)
    def test_admin_user_resource_access_does_not_raise(self, ctx: AccessContext) -> None:
        """
        场景 3：管理员用户 → check_resource_access 不抛出任何异常（即使 resource_check 返回 False）。

        # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
        Validates: Requirements 2.7
        """
        _mixin.check_resource_access(ctx, resource_check=lambda _: False)

    @given(
        ctx=access_context_strategy(
            user_st=authenticated_user_strategy(),
            perm_open_access_st=st.just(False),
        )
    )
    @settings(max_examples=100)
    def test_authenticated_non_admin_resource_check_false_raises_permission_denied(self, ctx: AccessContext) -> None:
        """
        场景 4：已认证普通用户 + resource_check 返回 False → check_resource_access 抛出 PermissionDenied。

        # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
        Validates: Requirements 2.7
        """
        with pytest.raises(PermissionDenied):
            _mixin.check_resource_access(ctx, resource_check=lambda _: False)

    @given(
        ctx=access_context_strategy(
            user_st=authenticated_user_strategy(),
            perm_open_access_st=st.just(False),
        )
    )
    @settings(max_examples=100)
    def test_authenticated_non_admin_resource_check_true_does_not_raise(self, ctx: AccessContext) -> None:
        """
        场景 5：已认证普通用户 + resource_check 返回 True → check_resource_access 不抛出任何异常。

        # Feature: backend-quality-to-10, Property 3: 权限检查异常类型正确性
        Validates: Requirements 2.7
        """
        _mixin.check_resource_access(ctx, resource_check=lambda _: True)
