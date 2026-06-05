"""Module for admin access."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.exceptions import PermissionDenied


def get_request_user(request: HttpRequest) -> Any | None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user
    return getattr(request, "auth", None)


def is_admin_user(user: Any | None) -> bool:
    return bool(
        user
        and (
            getattr(user, "is_admin", False) or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
        )
    )


def ensure_admin_request(
    request: HttpRequest,
    *,
    message: str = "无权限执行该操作",
    code: str = "PERMISSION_DENIED",
) -> None:
    if is_admin_user(get_request_user(request)):
        return
    raise PermissionDenied(message=message, code=code)


def apply_admin_access_filter(request: HttpRequest, qs: Any, policy: Any) -> Any:
    """在 Django admin get_queryset 中应用行级权限过滤.

    复用 CaseAccessPolicy / ContractAccessPolicy 的 filter_queryset,
    根据用户团队分配和显式授权过滤 queryset.
    """
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)
    return policy.filter_queryset(qs, request.user, org_access, perm_open_access)
