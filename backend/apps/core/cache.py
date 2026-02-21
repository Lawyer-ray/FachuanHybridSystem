"""
缓存配置模块 - 兼容层

此文件为向后兼容保留，实际实现已移至 infrastructure/cache.py
新代码建议使用: from apps.core.infrastructure import CacheKeys, CacheTimeout
"""

import warnings
from typing import Any, cast


def _safe_get_config(key: str, default: Any = None) -> Any:
    """安全获取配置，避免循环导入"""
    try:
        from .config import get_config

        return get_config(key, default)
    except Exception:
        return default


def get_cache_config() -> dict[str, Any]:
    """获取缓存配置"""
    redis_url = _safe_get_config("performance.cache.redis_url")

    if redis_url and redis_url != "redis://localhost:6379/0":
        location = redis_url
    else:
        redis_host = _safe_get_config("performance.cache.redis_host", "127.0.0.1")
        redis_port = _safe_get_config("performance.cache.redis_port", 6379)
        redis_db = _safe_get_config("performance.cache.redis_db", 0)
        redis_password = _safe_get_config("performance.cache.redis_password", "")

        if redis_password:
            location = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        else:
            location = f"redis://{redis_host}:{redis_port}/{redis_db}"

    default_timeout = _safe_get_config("performance.cache.default_timeout", 300)
    max_connections = _safe_get_config("performance.cache.max_connections", 50)
    socket_timeout = _safe_get_config("performance.cache.socket_timeout", 5)

    return {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": location,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": max_connections,
                    "retry_on_timeout": True,
                },
                "SOCKET_CONNECT_TIMEOUT": socket_timeout,
                "SOCKET_TIMEOUT": socket_timeout,
            },
            "KEY_PREFIX": _safe_get_config("performance.cache.key_prefix", "lawfirm"),
            "TIMEOUT": default_timeout,
        }
    }


class _CacheKeys:
    """缓存 key 定义（内部实现）"""

    USER_ORG_ACCESS = "user:org_access:{user_id}"
    USER_TEAMS = "user:teams:{user_id}"
    CASE_ACCESS_GRANTS = "case:access_grants:{user_id}"
    CASE_STAGES_CONFIG = "config:case_stages"
    LEGAL_STATUS_CONFIG = "config:legal_status"
    COURT_TOKEN = "court_token:{site_name}:{account}"

    @classmethod
    def user_org_access(cls, user_id: int) -> str:
        return cls.USER_ORG_ACCESS.format(user_id=user_id)

    @classmethod
    def user_teams(cls, user_id: int) -> str:
        return cls.USER_TEAMS.format(user_id=user_id)

    @classmethod
    def case_access_grants(cls, user_id: int) -> str:
        return cls.CASE_ACCESS_GRANTS.format(user_id=user_id)

    @classmethod
    def court_token(cls, site_name: str, account: str) -> str:
        return cls.COURT_TOKEN.format(site_name=site_name, account=account)


class _CacheTimeout:
    """缓存超时时间定义（内部实现）"""

    @staticmethod
    def get_short() -> int:
        return cast(int, _safe_get_config("performance.cache.timeout_short", 60))

    @staticmethod
    def get_medium() -> int:
        return cast(int, _safe_get_config("performance.cache.timeout_medium", 300))

    @staticmethod
    def get_long() -> int:
        return cast(int, _safe_get_config("performance.cache.timeout_long", 3600))

    @staticmethod
    def get_day() -> int:
        return cast(int, _safe_get_config("performance.cache.timeout_day", 86400))

    SHORT = 60
    MEDIUM = 300
    LONG = 3600
    DAY = 86400


# 通过 __getattr__ 在每次 `from apps.core.cache import X` 时触发 DeprecationWarning
_DEPRECATED_EXPORTS: dict[str, Any] = {
    "CacheKeys": _CacheKeys,
    "CacheTimeout": _CacheTimeout,
}


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED_EXPORTS:
        warnings.warn(
            "从 apps.core.cache 导入已废弃，请使用 apps.core.infrastructure.cache",
            DeprecationWarning,
            stacklevel=2,
        )
        return _DEPRECATED_EXPORTS[name]
    raise AttributeError(f"module 'apps.core.cache' has no attribute {name!r}")
