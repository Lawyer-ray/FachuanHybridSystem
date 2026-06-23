"""
组织访问控制中间件

OrgAccessMiddleware: 每个认证请求读取/计算 org_access，带 Redis 缓存。
ApiTrailingSlashMiddleware: 去除 API 路径尾部斜杠。
两者均为双模：sync 链直接执行，async 链返回协程。
"""

from __future__ import annotations

import asyncio
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from apps.core.infrastructure.cache import CacheKeys, CacheTimeout
from apps.organization.models import Lawyer

from .services.wiring import build_org_access_computation_service


class OrgAccessMiddleware:
    """为认证用户设置 request.org_access。双模：async 链使用 async cache + sync_to_async ORM。"""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return (
                self.get_response(request)
                if not asyncio.iscoroutinefunction(self.get_response)
                else self._pass(request)
            )

        if asyncio.iscoroutinefunction(self.get_response):
            return self._async_dispatch(request, user)
        return self._sync_dispatch(request, user)

    async def _pass(self, request: HttpRequest) -> HttpResponse:
        return await self.get_response(request)

    def _sync_dispatch(self, request: HttpRequest, user: Any) -> HttpResponse:
        cache_key = CacheKeys.user_org_access(user.id)
        org_access = cache.get(cache_key)

        if org_access is None:
            org_access = build_org_access_computation_service().compute(user)
            cache.set(cache_key, org_access, CacheTimeout.MEDIUM)

        request.org_access = org_access  # type: ignore[attr-defined]
        request.perm_open_access = bool(getattr(settings, "PERM_OPEN_ACCESS", False))  # type: ignore[attr-defined]
        return self.get_response(request)

    async def _async_dispatch(self, request: HttpRequest, user: Any) -> HttpResponse:
        from asgiref.sync import sync_to_async

        cache_key = CacheKeys.user_org_access(user.id)
        org_access = await cache.aget(cache_key)

        if org_access is None:
            # ORM 查询用 sync_to_async 包装，cache 用原生 async
            compute = sync_to_async(build_org_access_computation_service().compute, thread_sensitive=False)
            org_access = await compute(user)
            await cache.aset(cache_key, org_access, CacheTimeout.MEDIUM)

        request.org_access = org_access  # type: ignore[attr-defined]
        request.perm_open_access = bool(getattr(settings, "PERM_OPEN_ACCESS", False))  # type: ignore[attr-defined]
        return await self.get_response(request)


class ApiTrailingSlashMiddleware:
    """去除 /api/ 路径的尾部斜杠。双模：纯 CPU 无 I/O。"""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        path = request.path_info or ""
        if path.startswith("/api/") and path != "/api/" and path.endswith("/"):
            request.path_info = path.rstrip("/")

        if asyncio.iscoroutinefunction(self.get_response):
            return self.get_response(request)  # 返回协程
        return self.get_response(request)


def invalidate_user_org_cache(user_id: int) -> None:
    cache.delete(CacheKeys.user_org_access(user_id))
