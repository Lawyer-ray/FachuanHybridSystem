"""Token endpoint rate limiting middleware.

Protects the JWT token endpoint from brute-force attacks by applying
IP-based rate limiting before the request reaches the JWT handler.
"""

from __future__ import annotations

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
    """对 /api/v1/token/ 路径的请求进行限速。"""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        if request.path.startswith("/api/v1/token/") and request.method == "POST":
            ip = self._get_client_ip(request)
            cache_key = f"{_CACHE_PREFIX}:{ip}"
            current_bucket = int(time.time()) // _TOKEN_RATE_WINDOW
            bucket_key = f"{cache_key}:{current_bucket}"

            try:
                if cache.add(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5):
                    count = 1
                else:
                    try:
                        count = int(cache.incr(bucket_key))
                    except ValueError:
                        cache.set(bucket_key, 1, timeout=_TOKEN_RATE_WINDOW + 5)
                        count = 1
            except Exception:
                count = 0  # 缓存故障时放行

            if count > _TOKEN_RATE_LIMIT:
                logger.warning("JWT token endpoint rate limit exceeded for IP: %s", ip)
                return JsonResponse(
                    {"detail": "请求过于频繁，请稍后重试", "code": "RATE_LIMITED"},
                    status=429,
                )

        return self.get_response(request)

    def _get_client_ip(self, request: Any) -> str:
        xff: str | None = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        remote_addr: str = request.META.get("REMOTE_ADDR", "unknown")
        return remote_addr
