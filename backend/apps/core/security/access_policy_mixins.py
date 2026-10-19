"""Module for access policy mixins."""

from __future__ import annotations

from typing import Any

from django.utils.functional import Promise

from apps.core.exceptions import ForbiddenError
from apps.core.security.admin_access import is_admin_user

_StrOrPromise = str | Promise


class AuthzUserMixin:
    def is_authenticated(self, user: Any | None) -> bool:
        return bool(user and getattr(user, "is_authenticated", False))

    def is_authenticated_user(self, user: Any | None) -> bool:
        # 已登录用户均视为有权限，管理员权限仅用于系统级操作
        return self.is_authenticated(user)

    def is_admin(self, user: Any | None) -> bool:
        # 解耦（2026-10-19）：管理员判定委托 core.security.admin_access.is_admin_user
        # （2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员）
        return is_admin_user(user)

    def is_superuser(self, user: Any | None) -> bool:
        # 兼容别名（解耦 2026-10-19）：名实不符——实际口径是 is_admin 或 is_superuser，
        # 并非仅 Django is_superuser。调用方众多，保留旧名不改语义，内部委托 is_admin。
        return self.is_admin(user)

    def get_user_id(self, user: Any | None) -> int | None:
        return getattr(user, "id", None) if user else None


class OrgAllowedLawyersMixin(AuthzUserMixin):
    def get_allowed_lawyer_ids(self, user: Any | None, org_access: dict[str, Any] | None) -> set[int]:
        allowed_lawyers = set(org_access.get("lawyers", set())) if org_access else set()
        user_id = self.get_user_id(user)
        if user_id:
            allowed_lawyers.add(user_id)
        return allowed_lawyers


class DjangoPermsMixin(AuthzUserMixin):
    def ensure_authenticated(self, user: Any | None, message: _StrOrPromise = "用户未认证") -> None:
        if self.is_authenticated(user):
            return
        raise ForbiddenError(str(message))

    def ensure_admin(
        self,
        user: Any | None,
        *,
        perm_open_access: bool = False,
        message: _StrOrPromise = "权限不足",
    ) -> None:
        if perm_open_access:
            return
        self.ensure_authenticated(user)
        if self.is_superuser(user):
            return
        raise ForbiddenError(str(message))

    def has_perm(self, user: Any | None, perm: str) -> bool:
        return bool(user and self.is_authenticated(user) and (user.has_perm(perm) or self.is_superuser(user)))

    def ensure_has_perm(self, user: Any | None, perm: str, message: _StrOrPromise) -> None:
        self.ensure_authenticated(user)
        if self.has_perm(user, perm):
            return
        raise ForbiddenError(str(message))
