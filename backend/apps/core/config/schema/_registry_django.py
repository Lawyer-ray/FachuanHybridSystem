"""Django 核心配置注册"""

from .field import ConfigField


def register_django_configs(registry: dict[str, ConfigField]) -> None:
    registry["django.secret_key"] = ConfigField(
        name="django.secret_key",
        type=str,
        required=True,
        sensitive=True,
        env_var="SECRET_KEY",
        description="Django 密钥，用于加密和签名",
        min_length=50,
    )
    registry["django.debug"] = ConfigField(
        name="django.debug",
        type=bool,
        default=False,
        env_var="DEBUG",
        description="调试模式开关，生产环境必须为 False",
    )
    registry["django.allowed_hosts"] = ConfigField(
        name="django.allowed_hosts",
        type=list,
        default=["localhost", "127.0.0.1"],
        description="允许的主机列表",
    )
    registry["database.engine"] = ConfigField(
        name="database.engine",
        type=str,
        default="django.db.backends.mysql",
        choices=["django.db.backends.mysql", "django.db.backends.postgresql", "django.db.backends.sqlite3"],
        description="数据库引擎",
    )
    registry["database.name"] = ConfigField(
        name="database.name",
        type=str,
        required=False,
        env_var="DB_NAME",
        description="数据库名称",
    )
    registry["database.user"] = ConfigField(
        name="database.user",
        type=str,
        required=False,
        env_var="DB_USER",
        description="数据库用户名",
    )
    registry["database.password"] = ConfigField(
        name="database.password",
        type=str,
        required=False,
        sensitive=True,
        env_var="DB_PASSWORD",
        description="数据库密码",
    )
    registry["database.host"] = ConfigField(
        name="database.host",
        type=str,
        default="localhost",
        env_var="DB_HOST",
        description="数据库主机地址",
    )
    registry["database.port"] = ConfigField(
        name="database.port",
        type=int,
        default=3306,
        env_var="DB_PORT",
        min_value=1,
        max_value=65535,
        description="数据库端口",
    )
    registry["cors.allowed_origins"] = ConfigField(
        name="cors.allowed_origins",
        type=list,
        default=[],
        description="CORS 允许的来源列表",
    )
    registry["cors.trusted_origins"] = ConfigField(
        name="cors.trusted_origins",
        type=list,
        default=[],
        description="CSRF 信任的来源列表",
    )
