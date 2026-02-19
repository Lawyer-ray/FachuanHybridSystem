"""性能与缓存配置注册"""

from .field import ConfigField


def register_performance_configs(registry: dict[str, ConfigField]) -> None:
    # 限流
    registry["performance.rate_limit.default_requests"] = ConfigField(
        name="performance.rate_limit.default_requests", type=int, default=100,
        env_var="RATE_LIMIT_DEFAULT_REQUESTS", min_value=1, max_value=10000,
        description="默认请求限制（每窗口期）",
    )
    registry["performance.rate_limit.default_window"] = ConfigField(
        name="performance.rate_limit.default_window", type=int, default=60,
        env_var="RATE_LIMIT_DEFAULT_WINDOW", min_value=1, max_value=3600,
        description="默认限流窗口期（秒）",
    )
    registry["performance.rate_limit.auth_requests"] = ConfigField(
        name="performance.rate_limit.auth_requests", type=int, default=1000,
        env_var="RATE_LIMIT_AUTH_REQUESTS", min_value=1, max_value=100000,
        description="认证用户请求限制（每窗口期）",
    )
    registry["performance.rate_limit.auth_window"] = ConfigField(
        name="performance.rate_limit.auth_window", type=int, default=60,
        env_var="RATE_LIMIT_AUTH_WINDOW", min_value=1, max_value=3600,
        description="认证用户限流窗口期（秒）",
    )
    # Redis 缓存
    registry["performance.cache.redis_url"] = ConfigField(
        name="performance.cache.redis_url", type=str,
        default="redis://localhost:6379/0", env_var="REDIS_URL", description="Redis 连接 URL",
    )
    registry["performance.cache.redis_host"] = ConfigField(
        name="performance.cache.redis_host", type=str, default="127.0.0.1",
        env_var="REDIS_HOST", description="Redis 主机地址",
    )
    registry["performance.cache.redis_port"] = ConfigField(
        name="performance.cache.redis_port", type=int, default=6379,
        env_var="REDIS_PORT", min_value=1, max_value=65535, description="Redis 端口",
    )
    registry["performance.cache.redis_db"] = ConfigField(
        name="performance.cache.redis_db", type=int, default=0,
        env_var="REDIS_DB", min_value=0, max_value=15, description="Redis 数据库编号",
    )
    registry["performance.cache.redis_password"] = ConfigField(
        name="performance.cache.redis_password", type=str, default="", sensitive=True,
        env_var="REDIS_PASSWORD", description="Redis 密码",
    )
    registry["performance.cache.default_timeout"] = ConfigField(
        name="performance.cache.default_timeout", type=int, default=300,
        min_value=1, max_value=86400, description="默认缓存超时时间（秒）",
    )
    registry["performance.cache.max_connections"] = ConfigField(
        name="performance.cache.max_connections", type=int, default=50,
        min_value=1, max_value=1000, description="Redis 最大连接数",
    )
    registry["performance.cache.socket_timeout"] = ConfigField(
        name="performance.cache.socket_timeout", type=int, default=5,
        min_value=1, max_value=60, description="Redis Socket 超时时间（秒）",
    )
    registry["performance.cache.key_prefix"] = ConfigField(
        name="performance.cache.key_prefix", type=str, default="lawfirm", description="缓存键前缀",
    )
    registry["performance.cache.timeout_short"] = ConfigField(
        name="performance.cache.timeout_short", type=int, default=60,
        min_value=1, max_value=3600, description="短期缓存超时时间（秒）",
    )
    registry["performance.cache.timeout_medium"] = ConfigField(
        name="performance.cache.timeout_medium", type=int, default=300,
        min_value=1, max_value=3600, description="中期缓存超时时间（秒）",
    )
    registry["performance.cache.timeout_long"] = ConfigField(
        name="performance.cache.timeout_long", type=int, default=3600,
        min_value=1, max_value=86400, description="长期缓存超时时间（秒）",
    )
    registry["performance.cache.timeout_day"] = ConfigField(
        name="performance.cache.timeout_day", type=int, default=86400,
        min_value=1, max_value=604800, description="日缓存超时时间（秒）",
    )
    # Q_CLUSTER
    registry["performance.q_cluster.workers"] = ConfigField(
        name="performance.q_cluster.workers", type=int, default=4,
        min_value=1, max_value=32, description="Q_CLUSTER 工作进程数",
    )
    registry["performance.q_cluster.timeout"] = ConfigField(
        name="performance.q_cluster.timeout", type=int, default=60,
        min_value=1, max_value=3600, description="Q_CLUSTER 任务超时时间（秒）",
    )
    registry["performance.q_cluster.retry"] = ConfigField(
        name="performance.q_cluster.retry", type=int, default=60,
        min_value=1, max_value=3600, description="Q_CLUSTER 重试间隔（秒）",
    )
    registry["performance.q_cluster.queue_limit"] = ConfigField(
        name="performance.q_cluster.queue_limit", type=int, default=50,
        min_value=1, max_value=1000, description="Q_CLUSTER 队列限制",
    )
    registry["performance.q_cluster.bulk"] = ConfigField(
        name="performance.q_cluster.bulk", type=int, default=10,
        min_value=1, max_value=100, description="Q_CLUSTER 批量处理数量",
    )
    registry["performance.q_cluster.max_attempts"] = ConfigField(
        name="performance.q_cluster.max_attempts", type=int, default=1,
        min_value=1, max_value=10, description="Q_CLUSTER 最大尝试次数",
    )
