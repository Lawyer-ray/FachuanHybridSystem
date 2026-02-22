"""
中间件模块

提供请求指标、安全头、权限策略、ServiceLocator 作用域等中间件。
"""

import logging
import os
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from collections.abc import Callable


class RequestMetricsMiddleware:
    """请求指标记录中间件（WSGI callable 风格）"""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        from apps.core.telemetry import metrics as metrics_module

        enabled = not settings.DEBUG or os.environ.get("DJANGO_REQUEST_METRICS") == "1"

        start = time.monotonic()
        status_code = 500
        try:
            response = self.get_response(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            if enabled:
                duration_ms = int((time.monotonic() - start) * 1000)
                metrics_module.record_request(
                    method=request.method or "GET",
                    path=request.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )


class SecurityHeadersMiddleware:
    """按路径设置 Content-Security-Policy 响应头的中间件"""

    # /api/v1/docs 等文档路径不使用 API 策略
    _DOCS_SUFFIXES = ("/docs", "/schema", "/redoc", "/swagger")

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        self._apply_csp(request, response)
        return response

    def _apply_csp(self, request: HttpRequest, response: HttpResponse) -> None:
        path = request.path

        if path.startswith("/admin"):
            csp = getattr(settings, "CONTENT_SECURITY_POLICY_ADMIN", "")
            csp_ro = getattr(settings, "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY", "")
        elif path.startswith("/api/") and not any(path.endswith(s) for s in self._DOCS_SUFFIXES):
            csp = getattr(settings, "CONTENT_SECURITY_POLICY_API", "")
            csp_ro = getattr(settings, "CONTENT_SECURITY_POLICY_API_REPORT_ONLY", "")
        else:
            csp = getattr(settings, "CONTENT_SECURITY_POLICY", "")
            csp_ro = getattr(settings, "CONTENT_SECURITY_POLICY_REPORT_ONLY", "")

        if csp:
            response["Content-Security-Policy"] = csp
        if csp_ro:
            response["Content-Security-Policy-Report-Only"] = csp_ro


class PermissionsPolicyMiddleware:
    """设置 Permissions-Policy 响应头的中间件"""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        policy = getattr(settings, "PERMISSIONS_POLICY", "")
        if policy:
            response["Permissions-Policy"] = policy
        return response


class ServiceLocatorScopeMiddleware:
    """
    ServiceLocator 请求级作用域中间件

    每个 HTTP 请求在独立的 ServiceLocator scope 中执行，
    确保请求间服务实例不互相污染（基于 ContextVar 实现）。
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        from apps.core.interfaces import ServiceLocator

        with ServiceLocator.scope():
            return self.get_response(request)
