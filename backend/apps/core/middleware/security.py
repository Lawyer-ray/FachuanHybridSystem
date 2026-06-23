"""
中间件模块

提供安全头、权限策略、ServiceLocator 作用域等中间件。
所有中间件均为双模：sync 链直接执行，async 链返回协程由 Django handler await。

不设置 async_capable=True，让 Django 用 sync_to_async 包装中间件。
__call__ 在线程中运行，async 路径返回协程由 Django handler await。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def _init_dual_mode(mw: Any, get_response: Callable[..., Any]) -> None:
    """初始化双模中间件：检测 async 链并缓存结果。"""
    mw.get_response = get_response
    mw._is_async = asyncio.iscoroutinefunction(get_response)


class SecurityHeadersMiddleware:
    """按路径设置 Content-Security-Policy 响应头的中间件"""

    _DOCS_SUFFIXES = ("/docs", "/schema", "/redoc", "/swagger")

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        _init_dual_mode(self, get_response)

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_async:
            return self._adispatch(request)
        response = self.get_response(request)
        self._apply_csp(request, response)
        return response

    async def _adispatch(self, request: HttpRequest) -> HttpResponse:
        response = await self.get_response(request)
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
        _init_dual_mode(self, get_response)

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_async:
            return self._adispatch(request)
        response = self.get_response(request)
        self._set_policy(response)
        return response

    async def _adispatch(self, request: HttpRequest) -> HttpResponse:
        response = await self.get_response(request)
        self._set_policy(response)
        return response

    def _set_policy(self, response: HttpResponse) -> None:
        policy = getattr(settings, "PERMISSIONS_POLICY", "")
        if policy:
            response["Permissions-Policy"] = self._serialize_policy(policy)

    def _serialize_policy(self, policy: str | Mapping[str, object]) -> str:
        if isinstance(policy, str):
            return policy
        if not isinstance(policy, Mapping):
            return str(policy)

        directives: list[str] = []
        for feature, allowlist in policy.items():
            directives.append(f"{feature}={self._serialize_allowlist(allowlist)}")
        return ", ".join(directives)

    def _serialize_allowlist(self, allowlist: object) -> str:
        if allowlist in (None, [], (), set()):
            return "()"
        if allowlist == "*":
            return "*"
        if isinstance(allowlist, str):
            return f"({self._serialize_source(allowlist)})"
        if isinstance(allowlist, Iterable):
            values = " ".join(self._serialize_source(value) for value in allowlist)
            return f"({values})" if values else "()"
        return f"({self._serialize_source(allowlist)})"

    def _serialize_source(self, value: object) -> str:
        if value in {"self", "src", "*"}:
            return str(value)
        return f'"{value}"'


class ServiceLocatorScopeMiddleware:
    """
    ServiceLocator 请求级作用域中间件

    每个 HTTP 请求在独立的 ServiceLocator scope 中执行，
    确保请求间服务实例不互相污染（基于 ContextVar 实现）。
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        _init_dual_mode(self, get_response)

    def __call__(self, request: HttpRequest) -> Any:
        from apps.core.interfaces import ServiceLocator

        if self._is_async:
            return self._adispatch(request)
        with ServiceLocator.scope():
            return self.get_response(request)

    async def _adispatch(self, request: HttpRequest) -> HttpResponse:
        from apps.core.interfaces import ServiceLocator

        with ServiceLocator.scope():
            return await self.get_response(request)
