"""API 层公共辅助函数"""

from __future__ import annotations

from django.http import HttpRequest

from apps.organization.models import Lawyer


def get_request_user(request: HttpRequest) -> Lawyer | None:
    """从 Ninja request 中提取当前用户（兼容 auth 和 session 两种认证方式）"""
    return getattr(request, "auth", None) or getattr(request, "user", None)  # type: ignore[return-value]
