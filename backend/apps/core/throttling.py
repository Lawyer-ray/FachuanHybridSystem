"""
请求限流模块 - 委托给 infrastructure.throttling
"""

from apps.core.infrastructure.throttling import (
    RateLimiter,
    auth_limiter,
    default_limiter,
    get_rate_limit_config,
    rate_limit,
    rate_limit_by_user,
    rate_limit_from_settings,
    strict_limiter,
)

__all__ = [
    "RateLimiter",
    "auth_limiter",
    "default_limiter",
    "get_rate_limit_config",
    "rate_limit",
    "rate_limit_by_user",
    "rate_limit_from_settings",
    "strict_limiter",
]
