"""
请求限流模块
基于内存的请求限流实现
"""

import hashlib
import inspect
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest

from apps.core.exceptions import RateLimitError

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    请求限流器
    支持基于 IP、用户、或自定义 key 的限流
    """

    def __init__(
        self,
        requests: int = 100,
        window: int = 60,
        key_prefix: str = "ratelimit",
    ) -> None:
        """
        初始化限流器

        Args:
            requests: 时间窗口内允许的最大请求数
            window: 时间窗口(秒)
            key_prefix: 缓存 key 前缀
        """
        self.requests = requests
        self.window = window
        self.key_prefix = key_prefix

    def get_client_ip(self, request: HttpRequest) -> str:
        """获取客户端 IP"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        remote_addr = request.META.get("REMOTE_ADDR")
        trust_xff = (os.environ.get("DJANGO_TRUST_X_FORWARDED_FOR", "") or "").lower().strip() in ("true", "1", "yes")
        trusted_proxies_env = (os.environ.get("DJANGO_TRUSTED_PROXY_IPS", "") or "").strip()
        trusted_proxies = {ip.strip() for ip in trusted_proxies_env.split(",") if ip.strip()}
        trusted_hops_raw = (os.environ.get("DJANGO_TRUSTED_PROXY_HOPS", "") or "").strip()
        trusted_hops: int | None = None
        if trusted_hops_raw:
            try:
                trusted_hops = max(0, int(trusted_hops_raw))
            except ValueError:
                trusted_hops = None

        allow_unverified_xff = False
        if trust_xff and not trusted_proxies:
            try:
                from django.conf import settings

                allow_unverified_xff = bool(getattr(settings, "DEBUG", False))
            except (ImportError, AttributeError):
                allow_unverified_xff = False

        remote_addr_is_trusted = isinstance(remote_addr, str) and remote_addr and remote_addr in trusted_proxies
        if isinstance(x_forwarded_for, str) and x_forwarded_for and (remote_addr_is_trusted or allow_unverified_xff):
            parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
            if not parts:
                return remote_addr if isinstance(remote_addr, str) and remote_addr else "unknown"
            if trusted_hops is not None and trusted_hops > 0 and len(parts) > trusted_hops:
                return parts[-(trusted_hops + 1)]
            return parts[0]
        if isinstance(remote_addr, str) and remote_addr:
            return remote_addr
        return "unknown"

    def get_cache_key(self, request: HttpRequest, key_func: Callable[[HttpRequest], str] | None = None) -> str:
        """
        生成缓存 key

        Args:
            request: HTTP 请求
            key_func: 自定义 key 生成函数

        Returns:
            缓存 key
        """
        if key_func:
            identifier = key_func(request)
        else:
            # 默认使用 IP + 路径
            ip = self.get_client_ip(request)
            path = request.path
            identifier = f"{ip}:{path}"

        # 生成 hash 避免 key 过长
        key_hash = hashlib.md5(identifier.encode(), usedforsecurity=False).hexdigest()[:16]
        return f"{self.key_prefix}:{key_hash}"

    def is_allowed(
        self, request: HttpRequest, key_func: Callable[[HttpRequest], str] | None = None
    ) -> tuple[bool, dict[str, int]]:
        """
        检查请求是否被允许

        Args:
            request: HTTP 请求
            key_func: 自定义 key 生成函数

        Returns:
            (是否允许, 限流信息)
        """
        current_time = int(time.time())
        bucket = current_time // self.window
        window_end = (bucket + 1) * self.window
        cache_key = f"{self.get_cache_key(request, key_func)}:{bucket}"

        count: int
        if cache.add(cache_key, 1, timeout=self.window + 5):
            count = 1
        else:
            try:
                count = int(cache.incr(cache_key))
            except ValueError:
                cache.set(cache_key, 1, timeout=self.window + 5)
                count = 1

        remaining = max(0, self.requests - count)
        info = {
            "limit": self.requests,
            "remaining": remaining,
            "reset": window_end,
            "window": self.window,
        }

        if count > self.requests:
            return False, info
        return True, info


# 预定义的限流器实例
default_limiter = RateLimiter(requests=100, window=60)  # 每分钟 100 次
strict_limiter = RateLimiter(requests=10, window=60)  # 每分钟 10 次
auth_limiter = RateLimiter(requests=5, window=60)  # 登录限流:每分钟 5 次


def rate_limit(
    requests: int = 100,
    window: int = 60,
    key_func: Callable[[HttpRequest], str] | None = None,
    limiter: RateLimiter | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    限流装饰器

    Args:
        requests: 时间窗口内允许的最大请求数
        window: 时间窗口(秒)
        key_func: 自定义 key 生成函数
        limiter: 使用指定的限流器实例

    Usage:
        @router.get("/api/resource")
        @rate_limit(requests=10, window=60)
        def get_resource(request) -> None:
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
                _limiter = limiter or RateLimiter(requests=requests, window=window)
                allowed, info = _limiter.is_allowed(request, key_func)
                if not allowed:
                    wait_seconds = max(0, info["reset"] - int(time.time()))
                    raise RateLimitError(
                        message=f"请求过于频繁,请 {wait_seconds} 秒后重试",
                        errors={"retry_after": wait_seconds, **info},
                    )
                return await func(request, *args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            _limiter = limiter or RateLimiter(requests=requests, window=window)
            allowed, info = _limiter.is_allowed(request, key_func)
            if not allowed:
                wait_seconds = max(0, info["reset"] - int(time.time()))
                raise RateLimitError(
                    message=f"请求过于频繁,请 {wait_seconds} 秒后重试",
                    errors={"retry_after": wait_seconds, **info},
                )
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def key_func(request: HttpRequest) -> str:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"
        return f"ip:{RateLimiter().get_client_ip(request)}"

    return rate_limit(requests=requests, window=window, key_func=key_func)


def rate_limit_from_settings(
    kind: str, *, by_user: bool = True, key_func: Callable[[HttpRequest], str] | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    requests, window = get_rate_limit_config(kind, fallback_requests=100, fallback_window=60)
    if by_user:
        return rate_limit_by_user(requests=requests, window=window)
    return rate_limit(requests=requests, window=window, key_func=key_func)
