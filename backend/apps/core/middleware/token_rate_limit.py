"""Token endpoint rate limiting middleware.

Protects the JWT token endpoint from brute-force attacks by applying
IP-based rate limiting before the request reaches the JWT handler.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)

# 配置: 每分钟最多 10 次 token 请求（比登录更严格）
_TOKEN_RATE_LIMIT = 10
_TOKEN_RATE_WINDOW = 60  # seconds
_CACHE_PREFIX = "jwt_token_rl"


class TokenRateLimitMiddleware:
    """对 /api/v1/token/ 路径的请求进行限速。双模：支持 sync 和 async 链。"""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        self._is_async = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request: Any) -> Any:
        # 非 token 路径直接放行（无 I/O，无需 async）
        if not (request.path.startswith("/api/v1/token/") and request.method == "POST"):
            return self.get_response(request) if not self._is_async else self._pass(request)

        ip = self._get_client_ip(request)
        bucket_key = self._bucket_key(ip)

        if self._is_async:
            return self._check_and_dispatch_async(request, bucket_key, ip)
        return self._check_and_dispatch_sync(request, bucket_key, ip)

    async def _pass(self, request: Any) -> Any:
        return await self.get_response(request)

    def _check_and_dispatch_sync(self, request: Any, bucket_key: str, ip: str) -> Any:
        count = self._sync_check_rate(bucket_key)
        if count > _TOKEN_RATE_LIMIT:
            logger.warning("JWT token endpoint rate limit exceeded for IP: %s", ip)
            return JsonResponse(
                {"detail": "请求过于频繁，请稍后重试", "code": "RATE_LIMITED"},
                status=429,
            )
        return self.get_response(request)

    async def _check_and_dispatch_async(self, request: Any, bucket_key: str, ip: str) -> Any:
        count = await self._async_check_rate(bucket_key)
        if count > _TOKEN_RATE_LIMIT:
            logger.warning("JWT token endpoint rate limit exceeded for IP: %s", ip)
            return JsonResponse(
                {"detail": "请求过于频繁，请稍后重试", "code": "RATE_LIMITED"},
                status=429,
            )
        return await self.get_response(request)

    @staticmethod
    def _sync_check_rate(bucket_key: str) -> int:
        try:
            if cache.add(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5):
                return 1
            try:
                return int(cache.incr(bucket_key))
            except ValueError:
                cache.set(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5)
                return 1
        except Exception:
            return 0  # 缓存故障时放行

    @staticmethod
    async def _async_check_rate(bucket_key: str) -> int:
        try:
            if await cache.aget(bucket_key) is None:
                await cache.aset(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5)
                return 1
            try:
                val = await cache.aget(bucket_key)
                new_val = (val or 0) + 1
                await cache.aset(bucket_key, new_val, timeout=_TOKEN_RATE_WINDOW + 5)
                return new_val
            except Exception:
                await cache.aset(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5)
                return 1
        except Exception:
            return 0

    @staticmethod
    def _bucket_key(ip: str) -> str:
        current_bucket = int(time.time()) // _TOKEN_RATE_WINDOW
        return f"{_CACHE_PREFIX}:{ip}:{current_bucket}"

    @staticmethod
    def _get_client_ip(request: Any) -> str:
        xff: str | None = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        remote_addr: str = request.META.get("REMOTE_ADDR", "unknown")
        return remote_addr
