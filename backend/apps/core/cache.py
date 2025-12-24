"""
缓存配置模块
提供 Redis 缓存配置
"""
import os

def _safe_get_config(key, default=None):
    """安全获取配置，避免循环导入"""
    try:
        from .config import get_config
        return get_config(key, default)
    except Exception:
        return default


def get_cache_config() -> dict:
    """
    获取缓存配置

    从统一配置管理系统获取 Redis 配置，支持环境变量覆盖:
    - REDIS_URL: Redis 连接 URL (优先)
    - REDIS_HOST: Redis 主机地址
    - REDIS_PORT: Redis 端口
    - REDIS_DB: Redis 数据库编号
    - REDIS_PASSWORD: Redis 密码

    Returns:
        Django CACHES 配置字典
    """
    # 优先使用完整的 Redis URL
    redis_url = _safe_get_config("performance.cache.redis_url")
    
    if redis_url and redis_url != "redis://localhost:6379/0":
        # 如果配置了非默认的 Redis URL，直接使用
        location = redis_url
    else:
        # 否则从分离的配置项构建 URL
        redis_host = _safe_get_config("performance.cache.redis_host", "127.0.0.1")
        redis_port = _safe_get_config("performance.cache.redis_port", 6379)
        redis_db = _safe_get_config("performance.cache.redis_db", 0)
        redis_password = _safe_get_config("performance.cache.redis_password", "")

        if redis_password:
            location = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        else:
            location = f"redis://{redis_host}:{redis_port}/{redis_db}"

    # 获取其他缓存配置
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


# 缓存 key 常量
class CacheKeys:
    """缓存 key 定义"""

    # 用户相关
    USER_ORG_ACCESS = "user:org_access:{user_id}"  # 用户组织访问权限
    USER_TEAMS = "user:teams:{user_id}"  # 用户团队列表

    # 案件相关
    CASE_ACCESS_GRANTS = "case:access_grants:{user_id}"  # 用户案件访问授权

    # 配置相关
    CASE_STAGES_CONFIG = "config:case_stages"  # 案件阶段配置
    LEGAL_STATUS_CONFIG = "config:legal_status"  # 诉讼地位配置

    # 法院系统 Token 相关
    COURT_TOKEN = "court_token:{site_name}:{account}"  # 法院系统 Token

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


# 缓存超时时间（秒）
class CacheTimeout:
    """缓存超时时间定义"""
    
    @staticmethod
    def get_short() -> int:
        """短期缓存（1分钟）"""
        return _safe_get_config("performance.cache.timeout_short", 60)
    
    @staticmethod
    def get_medium() -> int:
        """中期缓存（5分钟）"""
        return _safe_get_config("performance.cache.timeout_medium", 300)
    
    @staticmethod
    def get_long() -> int:
        """长期缓存（1小时）"""
        return _safe_get_config("performance.cache.timeout_long", 3600)
    
    @staticmethod
    def get_day() -> int:
        """日缓存（1天）"""
        return _safe_get_config("performance.cache.timeout_day", 86400)
    
    # 保持向后兼容的常量
    SHORT = 60
    MEDIUM = 300
    LONG = 3600
    DAY = 86400
