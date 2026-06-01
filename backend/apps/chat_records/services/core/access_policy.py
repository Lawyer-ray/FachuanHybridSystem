"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import PermissionDenied
from apps.core.security.admin_access import is_admin_user


def ensure_can_access_project(*, user: Any | None, project: Any) -> None:
    if is_admin_user(user):
        return
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("无权限访问该项目")
    if getattr(project, "created_by_id", None) and getattr(user, "id", None) == project.created_by_id:
        return
    raise PermissionDenied("无权限访问该项目")
