"""
请求限流模块
基于 Redis 或内存的请求限流实现
"""
import time
import hashlib
from typing import Optional, Tuple
from functools import wraps
from django.core.cache import cache
from django.http import HttpRequest
from ninja.errors import HttpError


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
    ):
        """
        初始化限流器

        Args:
            requests: 时间窗口内允许的最大请求数
            window: 时间窗口（秒）
            key_prefix: 缓存 key 前缀
        """
        self.requests = requests
        self.window = window
        self.key_prefix = key_prefix

    def get_client_ip(self, request: HttpRequest) -> str:
        """获取客户端 IP"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def get_cache_key(self, request: HttpRequest, key_func: Optional[callable] = None) -> str:
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
        key_hash = hashlib.md5(identifier.encode()).hexdigest()[:16]
        return f"{self.key_prefix}:{key_hash}"

    def is_allowed(self, request: HttpRequest, key_func: Optional[callable] = None) -> Tuple[bool, dict]:
        """
        检查请求是否被允许

        Args:
            request: HTTP 请求
            key_func: 自定义 key 生成函数

        Returns:
            (是否允许, 限流信息)
        """
        cache_key = self.get_cache_key(request, key_func)
        current_time = int(time.time())
        window_start = current_time - self.window

        # 获取当前窗口的请求记录
        request_times = cache.get(cache_key, [])

        # 过滤掉窗口外的请求
        request_times = [t for t in request_times if t > window_start]

        # 计算剩余配额
        remaining = max(0, self.requests - len(request_times))
        reset_time = current_time + self.window

        info = {
            "limit": self.requests,
            "remaining": remaining,
            "reset": reset_time,
            "window": self.window,
        }

        if len(request_times) >= self.requests:
            return False, info

        # 记录本次请求
        request_times.append(current_time)
        cache.set(cache_key, request_times, self.window + 10)

        info["remaining"] = remaining - 1
        return True, info


# 预定义的限流器实例
default_limiter = RateLimiter(requests=100, window=60)  # 每分钟 100 次
strict_limiter = RateLimiter(requests=10, window=60)    # 每分钟 10 次
auth_limiter = RateLimiter(requests=5, window=60)       # 登录限流：每分钟 5 次


def rate_limit(
    requests: int = 100,
    window: int = 60,
    key_func: Optional[callable] = None,
    limiter: Optional[RateLimiter] = None,
):
    """
    限流装饰器

    Args:
        requests: 时间窗口内允许的最大请求数
        window: 时间窗口（秒）
        key_func: 自定义 key 生成函数
        limiter: 使用指定的限流器实例

    Usage:
        @router.get("/api/resource")
        @rate_limit(requests=10, window=60)
        def get_resource(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # 使用指定的限流器或创建新的
            _limiter = limiter or RateLimiter(requests=requests, window=window)

            allowed, info = _limiter.is_allowed(request, key_func)

            if not allowed:
                raise HttpError(
                    429,
                    f"请求过于频繁，请 {info['reset'] - int(time.time())} 秒后重试"
                )

            # 执行原函数
            response = func(request, *args, **kwargs)

            # 可以在这里添加限流响应头（如果需要）
            # response['X-RateLimit-Limit'] = str(info['limit'])
            # response['X-RateLimit-Remaining'] = str(info['remaining'])

            return response

        return wrapper
    return decorator


def rate_limit_by_user(requests: int = 100, window: int = 60):
    """
    基于用户的限流装饰器
    已登录用户使用用户 ID，未登录使用 IP
    """
    def key_func(request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"
        return f"ip:{RateLimiter().get_client_ip(request)}"

    return rate_limit(requests=requests, window=window, key_func=key_func)
