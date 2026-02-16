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
