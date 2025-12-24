"""
Django 日志配置模块
提供结构化日志配置

Docker 环境支持：
- 自动检测 Docker 环境
- 优先输出到 stdout/stderr（Docker 日志收集）
- 同时保留文件日志（持久化到 Volume）
"""
import os
import sys


def _safe_get_config(key, default=None):
    """安全获取配置，避免循环导入"""
    try:
        from .config import get_config
        return get_config(key, default)
    except Exception:
        return default


def _is_docker_environment() -> bool:
    """
    检测是否在 Docker 环境中运行
    
    检测方法：
    1. 检查 /.dockerenv 文件
    2. 检查 /proc/1/cgroup 中是否包含 docker
    3. 检查环境变量 DOCKER_CONTAINER
    """
    # 方法1: 检查 .dockerenv 文件
    if os.path.exists('/.dockerenv'):
        return True
    
    # 方法2: 检查 cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            if 'docker' in f.read():
                return True
    except (FileNotFoundError, PermissionError):
        pass
    
    # 方法3: 检查环境变量
    if os.environ.get('DOCKER_CONTAINER') == 'true':
        return True
    
    # 方法4: 检查 DATABASE_PATH 是否为 Docker 路径
    if os.environ.get('DATABASE_PATH', '').startswith('/app/'):
        return True
    
    return False


def get_logging_config(base_dir, debug: bool = True) -> dict:
    """
    获取日志配置

    从统一配置管理系统获取日志配置参数
    
    Docker 环境特性：
    - 优先输出到 stdout（Docker 日志收集）
    - 使用 JSON 格式便于日志聚合
    - 同时保留文件日志到 Volume

    Args:
        base_dir: 项目根目录
        debug: 是否为调试模式

    Returns:
        Django LOGGING 配置字典
    """
    is_docker = _is_docker_environment()
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    # 从配置系统获取日志参数
    file_max_size = _safe_get_config("logging.file_max_size", 10 * 1024 * 1024)  # 10MB
    api_backup_count = _safe_get_config("logging.api_backup_count", 5)
    error_backup_count = _safe_get_config("logging.error_backup_count", 10)
    sql_backup_count = _safe_get_config("logging.sql_backup_count", 3)
    
    # 获取日志级别配置
    console_level = _safe_get_config("logging.console_level", "DEBUG" if debug else "INFO")
    file_level = _safe_get_config("logging.file_level", "INFO")
    error_level = _safe_get_config("logging.error_level", "ERROR")
    django_level = _safe_get_config("logging.django_level", "INFO")
    request_level = _safe_get_config("logging.request_level", "WARNING")
    apps_level = _safe_get_config("logging.apps_level", "DEBUG" if debug else "INFO")
    root_level = _safe_get_config("logging.root_level", "WARNING")

    # Docker 环境使用 JSON 格式，便于日志聚合
    console_formatter = "json" if is_docker and not debug else "simple"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} - {message}",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "simple": {
                "format": "[{asctime}] {levelname} - {message}",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "apps.core.logging.JsonFormatter",
            },
            "docker": {
                # Docker 友好格式：包含时间戳、级别、模块信息
                "format": "{asctime} | {levelname:8} | {name} | {message}",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            "require_debug_true": {
                "()": "django.utils.log.RequireDebugTrue",
            },
            "require_debug_false": {
                "()": "django.utils.log.RequireDebugFalse",
            },
        },
        "handlers": {
            # 控制台输出（Docker 环境下输出到 stdout）
            "console": {
                "level": console_level,
                "class": "logging.StreamHandler",
                "stream": sys.stdout,  # 明确指定 stdout
                "formatter": console_formatter,
            },
            # 错误输出到 stderr（Docker 环境下便于区分）
            "console_error": {
                "level": "ERROR",
                "class": "logging.StreamHandler",
                "stream": sys.stderr,  # 错误输出到 stderr
                "formatter": console_formatter,
            },
            "file_api": {
                "level": file_level,
                "class": "logging.handlers.RotatingFileHandler",
                "filename": os.path.join(log_dir, "api.log"),
                "maxBytes": file_max_size,
                "backupCount": api_backup_count,
                "formatter": "verbose",
                "encoding": "utf-8",
            },
            "file_error": {
                "level": error_level,
                "class": "logging.handlers.RotatingFileHandler",
                "filename": os.path.join(log_dir, "error.log"),
                "maxBytes": file_max_size,
                "backupCount": error_backup_count,
                "formatter": "verbose",
                "encoding": "utf-8",
            },
            "file_sql": {
                "level": "DEBUG",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": os.path.join(log_dir, "sql.log"),
                "maxBytes": file_max_size,
                "backupCount": sql_backup_count,
                "formatter": "simple",
                "encoding": "utf-8",
                "filters": ["require_debug_true"],
            },
        },
        "loggers": {
            "django": {
                "handlers": ["console", "console_error", "file_error"],
                "level": django_level,
                "propagate": True,
            },
            "django.request": {
                "handlers": ["console", "console_error", "file_error"],
                "level": request_level,
                "propagate": False,
            },
            "django.db.backends": {
                "handlers": ["file_sql"] if debug else [],
                "level": "DEBUG" if debug else "INFO",
                "propagate": False,
            },
            "api": {
                "handlers": ["console", "console_error", "file_api", "file_error"],
                "level": apps_level,
                "propagate": False,
            },
            "apps": {
                "handlers": ["console", "console_error", "file_api", "file_error"],
                "level": apps_level,
                "propagate": False,
            },
            # Gunicorn 日志（Docker 生产环境）
            "gunicorn.error": {
                "handlers": ["console", "console_error"],
                "level": "INFO",
                "propagate": False,
            },
            "gunicorn.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console", "console_error", "file_error"],
            "level": root_level,
        },
    }
    
    return config


class JsonFormatter:
    """JSON 格式化器，用于结构化日志输出"""

    def __init__(self):
        import json
        self.json = json

    def format(self, record):
        import traceback
        from datetime import datetime

        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "user"):
            log_data["user"] = str(record.user)
        if hasattr(record, "errors"):
            log_data["errors"] = record.errors

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = "".join(traceback.format_exception(*record.exc_info))

        return self.json.dumps(log_data, ensure_ascii=False)
