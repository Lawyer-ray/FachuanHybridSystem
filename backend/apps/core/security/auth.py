"""
认证模块

提供多种认证方式:
- JWTAuth: 仅 JWT 认证(用于前端 API)
- SessionAuth: 仅 Django Session 认证(用于 Admin 页面)
- JWTOrSessionAuth: JWT 或 Session 认证(用于需要同时支持前端和 Admin 的 API)
"""

import logging
import os
from typing import Any

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from ninja.security import APIKeyHeader, HttpBearer
from ninja_jwt.authentication import JWTAuth

from apps.core.exceptions import PermissionDenied

logger = logging.getLogger("apps.core.auth")


class SessionAuth(APIKeyHeader):
    """
    Django Session 认证

    用于 Django Admin 后台页面中的 AJAX 请求
    """

    param_name: str = "X-Session-Auth"  # 不实际使用,只是为了满足基类要求

    def authenticate(self, request: Any, key: Any | None = None) -> Any:
        """
        检查 Django Session 认证
        """
        if request.user and request.user.is_authenticated:
            return request.user
        return None


class JWTOrSessionAuth(HttpBearer):
    """
    JWT 或 Django Session 认证

    优先使用 JWT 认证,如果没有 JWT token 则尝试 Session 认证.
    适用于需要同时支持前端 API 调用和 Django Admin 后台 AJAX 请求的接口.
    """

    openapi_scheme: str = "bearer"

    def __init__(self) -> None:
        super().__init__()
        self._jwt_auth = JWTAuth()

    def __call__(self, request: Any) -> Any:
        """
        重写 __call__ 方法,先尝试 JWT 认证,再尝试 Session 认证
        """
        # 1. 尝试从 Authorization header 获取 JWT token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                user = self._jwt_auth.authenticate(request, token)
                if user:
                    return user
            except Exception as e:
                if getattr(settings, "DEBUG", False) or os.environ.get("DJANGO_JWT_AUTH_LOG", "").lower() in (
                    "true",
                    "1",
                    "yes",
                ):
                    logger.info("jwt_auth_failed", extra={"error_type": type(e).__name__})

        # 2. 再尝试 Session 认证(Django Admin 登录)
        if hasattr(request, "user") and request.user and request.user.is_authenticated:
            if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
                reason = CsrfViewMiddleware(lambda _req: None).process_view(request, lambda _req: None, (), {})  # type: ignore[return-value, arg-type, arg-type]
                if reason is not None:
                    raise PermissionDenied(message="CSRF 校验失败", code="CSRF_FAILED")
            return request.user

        return None

    def authenticate(self, request: Any, token: Any | None = None) -> Any:
        """
        保留此方法以兼容 HttpBearer 接口
        """
        return self.__call__(request)
