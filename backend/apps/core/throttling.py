"""
请求限流模块 - 兼容层

此文件为向后兼容保留，实际实现已移至 infrastructure/throttling.py
新代码建议使用: from apps.core.infrastructure import RateLimiter
"""

import warnings

warnings.warn(
    "从 apps.core.throttling 导入已废弃，请使用 apps.core.infrastructure.throttling",
    DeprecationWarning,
    stacklevel=2,
)

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
