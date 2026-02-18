"""权限检查混入模块

提供 AccessContext 数据类和 PermissionMixin 混入类，
封装三层权限判断逻辑：开放访问 → 管理员 → 资源访问检查。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.core.exceptions import AuthenticationError, PermissionDenied


@dataclass(frozen=True)
class AccessContext:
    """访问上下文，封装权限检查所需的用户和权限信息。"""

    user: Any | None
    org_access: dict[str, Any] | None
    perm_open_access: bool


class PermissionMixin:
    """权限检查混入类，提供统一的权限判断方法。"""

    def check_authenticated(self, ctx: AccessContext) -> None:
        """检查用户是否已认证。

        若用户未认证且 perm_open_access 为 False，抛出 AuthenticationError。
        """
        if (not ctx.user or not getattr(ctx.user, "is_authenticated", False)) and not ctx.perm_open_access:
            raise AuthenticationError("请先登录")

    def is_admin(self, ctx: AccessContext) -> bool:
        """检查当前用户是否为管理员。"""
        return bool(ctx.user and getattr(ctx.user, "is_admin", False))

    def has_open_access(self, ctx: AccessContext) -> bool:
        """检查是否具有开放访问权限。"""
        return ctx.perm_open_access

    def check_resource_access(
        self,
        ctx: AccessContext,
        resource_check: Callable[[AccessContext], bool],
        error_message: str = "无权限访问该资源",
    ) -> None:
        """通用资源访问检查。

        检查顺序：开放访问 → 管理员 → 认证状态 → 资源级权限。
        若所有检查均未通过，抛出 PermissionDenied。
        """
        if self.has_open_access(ctx):
            return
        if self.is_admin(ctx):
            return
        self.check_authenticated(ctx)
        if not resource_check(ctx):
            raise PermissionDenied(error_message)
