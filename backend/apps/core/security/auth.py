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

    @staticmethod
    def _load_user(user_id: int) -> Any | None:
        """按 id 取用户，取不到返回 None（票据兑现失败的上游）。

        与 ``JWTAuth.get_user`` 同为同步 DB 查询——票据路径与既有 JWT 路径
        的调用上下文完全一致，不额外引入 async 边界。

        ``is_active`` 必须与 JWT 路径同口径（ninja_jwt 的 ``get_user`` 拒
        inactive），否则停用账号会经由票据重新获得访问权。

        用 ``get_user_model()`` 而非 import ``Lawyer``：core 禁止新增对业务
        app 的 import（见 ``tests/ci/structure/test_core_no_business_deps``），
        且本项目 AUTH_USER_MODEL 就是 Lawyer。
        """
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        try:
            user = user_model.objects.get(id=user_id)
        except user_model.DoesNotExist:
            return None
        return user if getattr(user, "is_active", False) else None

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
        #    （用于 <img>/<iframe>/<a download> 等带不上请求头的场景，均为 GET）。
        #
        #    安全审计（2026Q4 M-2）：原先这里直接收 JWT，导致完整 JWT 落入 nginx
        #    access log / 浏览器历史 / Referer。现在 query 只接受短时一次性下载票据
        #    （apps.core.security.download_tickets），JWT 一律走 Authorization 头。
        #    POST/PUT/DELETE 的 query 参数会随 URL 进访问日志/中间代理日志，同样不收。
        if not token and request.method in ("GET", "HEAD"):
            ticket = request.GET.get("ticket")
            if ticket:
                from apps.core.security.download_tickets import TicketError, consume_download_ticket

                try:
                    user_id = consume_download_ticket(ticket)
                except TicketError:
                    user_id = None
                if user_id is not None:
                    ticket_user = self._load_user(user_id)
                    if ticket_user is not None:
                        return ticket_user
                # 票据无效时不再回退 JWT query（那正是要堵住的洞），继续走 Session
                logger.info("download_ticket_rejected", extra={"path": request.path[:120]})

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
