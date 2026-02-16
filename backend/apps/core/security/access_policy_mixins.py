"""Module for access policy mixins."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ForbiddenError


class AuthzUserMixin:
    def is_authenticated(self, user: Any | None) -> bool:
        return bool(user and getattr(user, "is_authenticated", False))

    def is_admin(self, user: Any | None) -> bool:
        return bool(user and getattr(user, "is_admin", False))

    def is_superuser(self, user: Any | None) -> bool:
        return bool(user and getattr(user, "is_superuser", False))

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
    def ensure_authenticated(self, user: Any | None, message: str = "用户未认证") -> None:
        if self.is_authenticated(user):
            return
        raise ForbiddenError(message)

    def ensure_admin(
        self,
        user: Any | None,
        *,
        perm_open_access: bool = False,
        message: str = "权限不足",
    ) -> None:
        if perm_open_access:
            return
        self.ensure_authenticated(user)
        if self.is_admin(user) or self.is_superuser(user):
            return
        raise ForbiddenError(message)

    def has_perm(self, user: Any | None, perm: str) -> bool:
        return bool(
            user
            and self.is_authenticated(user)
            and (user.has_perm(perm) or self.is_admin(user) or self.is_superuser(user))
        )

    def ensure_has_perm(self, user: Any | None, perm: str, message: str) -> None:
        self.ensure_authenticated(user)
        if self.has_perm(user, perm):
            return
        raise ForbiddenError(message)
