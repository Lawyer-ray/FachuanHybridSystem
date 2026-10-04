"""
认证模块

提供多种认证方式:
- JWTAuth: 仅 JWT 认证(用于前端 API)
- JWTOrSessionAuth: JWT 或 Session 认证(用于需要同时支持前端和 Admin 的 API)
"""

import logging
import os
from typing import Any

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from ninja.security import HttpBearer
from ninja_jwt.authentication import JWTAuth

from apps.core.exceptions import PermissionDenied

logger = logging.getLogger("apps.core.auth")


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
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # 2. 如果 header 中没有 token,仅对安全方法（GET/HEAD）尝试从 query parameter 获取
        #    （用于 window.open 下载场景，均为 GET）。POST/PUT/DELETE 的 query 参数会随
        #    URL 进访问日志/中间代理日志，必须改走 Authorization 头（安全审计）
        if not token and request.method in ("GET", "HEAD"):
            token = request.GET.get("token")

        if token:
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

        # 3. 再尝试 Session 认证(Django Admin 登录)
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
