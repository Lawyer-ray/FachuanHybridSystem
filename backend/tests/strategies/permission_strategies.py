"""权限相关 Hypothesis 策略

为 PermissionMixin 属性测试提供随机 AccessContext 生成策略。
"""

from __future__ import annotations

import types
from typing import Any

from hypothesis import strategies as st

from apps.core.permissions import AccessContext


def _make_user(is_authenticated: bool, is_admin: bool) -> Any:
    """构造 mock 用户对象。"""
    return types.SimpleNamespace(is_authenticated=is_authenticated, is_admin=is_admin)


@st.composite
def unauthenticated_user_strategy(draw: st.DrawFn) -> Any:
    """生成未认证用户：is_authenticated=False 或 user=None。"""
    use_none: bool = draw(st.booleans())
    if use_none:
        return None
    return _make_user(is_authenticated=False, is_admin=False)


@st.composite
def authenticated_user_strategy(draw: st.DrawFn) -> Any:
    """生成已认证普通用户：is_authenticated=True, is_admin=False。"""
    return _make_user(is_authenticated=True, is_admin=False)


@st.composite
def admin_user_strategy(draw: st.DrawFn) -> Any:
    """生成管理员用户：is_authenticated=True, is_admin=True。"""
    return _make_user(is_authenticated=True, is_admin=True)


@st.composite
def access_context_strategy(
    draw: st.DrawFn,
    user_st: st.SearchStrategy[Any],
    perm_open_access_st: st.SearchStrategy[bool],
) -> AccessContext:
    """从给定的用户策略和 perm_open_access 策略组合 AccessContext。"""
    user: Any = draw(user_st)
    perm_open_access: bool = draw(perm_open_access_st)
    org_access: dict[str, Any] | None = draw(
        st.one_of(
            st.none(),
            st.dictionaries(st.text(min_size=1, max_size=10), st.text(max_size=20)),
        )
    )
    return AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
