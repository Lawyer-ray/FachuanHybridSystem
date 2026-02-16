"""
基础设施模块

提供缓存、监控、限流、健康检查等基础设施功能.
"""

# 缓存
from .cache import (
    CacheKeys,
    CacheTimeout,
    bump_cache_version,
    delete_cache_key,
    get_cache_config,
    invalidate_case_access_cache,
    invalidate_user_access_context,
    invalidate_user_org_access_cache,
    invalidate_users_access_context,
)

# 健康检查
from .health import ComponentHealth, HealthChecker, HealthStatus, SystemHealth

# 监控
from .monitoring import PerformanceMonitor, monitor_api, monitor_operation

# 资源监控
from .resource_monitor import (
    ResourceMonitor,
    ResourceThresholds,
    ResourceUsage,
    get_resource_status,
    get_resource_usage,
    resource_monitor,
    start_resource_monitoring,
    stop_resource_monitoring,
)

# 限流
from .throttling import RateLimiter, auth_limiter, default_limiter, rate_limit, rate_limit_by_user, strict_limiter

__all__ = [
    # 缓存
    "CacheKeys",
    "CacheTimeout",
    "bump_cache_version",
    "delete_cache_key",
    "get_cache_config",
    "invalidate_case_access_cache",
    "invalidate_user_access_context",
    "invalidate_user_org_access_cache",
    "invalidate_users_access_context",
    # 监控
    "PerformanceMonitor",
    "monitor_api",
    "monitor_operation",
    # 资源监控
    "ResourceMonitor",
    "ResourceUsage",
    "ResourceThresholds",
    "resource_monitor",
    "get_resource_status",
    "get_resource_usage",
    "start_resource_monitoring",
    "stop_resource_monitoring",
    # 限流
    "RateLimiter",
    "default_limiter",
    "strict_limiter",
    "auth_limiter",
    "rate_limit",
    "rate_limit_by_user",
    # 健康检查
    "HealthStatus",
    "ComponentHealth",
    "SystemHealth",
    "HealthChecker",
]
