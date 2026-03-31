"""数据库、缓存、磁盘、依赖检查器"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.core.infrastructure.cache import CacheTimeout
from apps.core.utils.path import Path

from ._models import ComponentHealth, HealthStatus

logger = logging.getLogger(__name__)

__all__ = ["check_database", "check_cache", "check_disk_space", "check_dependencies"]


def check_database() -> ComponentHealth:
    """检查数据库连接"""
    start = time.time()
    diagnostic_info: dict[str, Any] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        latency = (time.time() - start) * 1000

        try:
            db_path = getattr(settings, "DATABASES", {}).get("default", {}).get("NAME", "")
            db_file = Path(str(db_path)) if db_path else None
            if db_file and db_file.exists():
                stat = db_file.stat()
                diagnostic_info.update(
                    {
                        "database_path": str(db_file),
                        "database_size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "last_modified": time.ctime(stat.st_mtime),
                        "readable": os.access(str(db_file), os.R_OK),
                        "writable": os.access(str(db_file), os.W_OK),
                    }
                )

            diagnostic_info.update(
                {
                    "connection_vendor": connection.vendor,
                    "connection_queries_count": len(connection.queries),
                }
            )

        except Exception as diag_e:
            logger.exception("操作失败")
            diagnostic_info["diagnostic_error"] = str(diag_e)

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=latency,
            message="Database connection OK",
            diagnostic_info=diagnostic_info,
        )
    except Exception as e:
        try:
            db_path = getattr(settings, "DATABASES", {}).get("default", {}).get("NAME", "")
            db_file = Path(str(db_path)) if db_path else None
            diagnostic_info.update(
                {
                    "database_path": db_path,
                    "path_exists": db_file.exists() if db_file else False,
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                }
            )

            if db_file:
                db_dir = db_file.parent
                diagnostic_info.update(
                    {
                        "directory_exists": db_dir.exists(),
                        "directory_writable": os.access(str(db_dir), os.W_OK) if db_dir.exists() else False,
                    }
                )
        except Exception as diag_e:
            logger.exception("操作失败")
            diagnostic_info["diagnostic_collection_error"] = str(diag_e)

        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {e!s}",
            diagnostic_info=diagnostic_info,
        )


def check_cache() -> ComponentHealth:
    """检查缓存连接"""
    start = time.time()
    test_key = "_health_check_"
    test_value = "ok"
    diagnostic_info: dict[str, Any] = {}

    try:
        cache_config = getattr(settings, "CACHES", {}).get("default", {})
        diagnostic_info.update(
            {
                "cache_backend": cache_config.get("BACKEND", "unknown"),
                "cache_location": cache_config.get("LOCATION", "unknown"),
            }
        )

        cache.set(test_key, test_value, CacheTimeout.get_short())
        result = cache.get(test_key)
        cache.delete(test_key)

        latency = (time.time() - start) * 1000

        if result == test_value:
            return ComponentHealth(
                name="cache",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Cache connection OK",
                diagnostic_info=diagnostic_info,
            )
        else:
            diagnostic_info["read_write_test"] = {"expected": test_value, "actual": result}
            return ComponentHealth(
                name="cache",
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                message="Cache read/write mismatch",
                diagnostic_info=diagnostic_info,
            )
    except Exception as e:
        logger.exception("操作失败")
        diagnostic_info.update({"error_type": type(e).__name__, "error_details": str(e)})

        return ComponentHealth(
            name="cache",
            status=HealthStatus.DEGRADED,
            message=f"Cache error: {e!s}",
            diagnostic_info=diagnostic_info,
        )


def check_disk_space() -> ComponentHealth:
    """检查磁盘空间"""
    diagnostic_info: dict[str, Any] = {}

    try:
        media_root = getattr(settings, "MEDIA_ROOT", "/tmp")  # nosec B108
        stat = os.statvfs(str(media_root))

        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_percent = ((total - free) / total) * 100 if total > 0 else 0

        status = HealthStatus.HEALTHY
        if used_percent > 90:
            status = HealthStatus.UNHEALTHY
        elif used_percent > 80:
            status = HealthStatus.DEGRADED

        diagnostic_info.update(
            {
                "media_root": str(media_root),
                "filesystem_type": "unknown",
                "total_inodes": stat.f_files,
                "free_inodes": stat.f_ffree,
                "block_size": stat.f_frsize,
            }
        )

        important_paths = [
            (
                "database_dir",
                str(Path(str(getattr(settings, "DATABASES", {}).get("default", {}).get("NAME", "/tmp"))).parent),  # nosec B108
            ),
            ("logs_dir", "/app/logs"),
            ("static_dir", getattr(settings, "STATIC_ROOT", "/tmp")),  # nosec B108
        ]

        for path_name, path in important_paths:
            if Path(str(path)).exists():
                try:
                    path_stat = os.statvfs(path)
                    path_total = path_stat.f_blocks * path_stat.f_frsize
                    path_free = path_stat.f_bavail * path_stat.f_frsize
                    path_used_percent = ((path_total - path_free) / path_total) * 100 if path_total > 0 else 0

                    diagnostic_info[f"{path_name}_usage"] = {
                        "path": path,
                        "total_gb": round(path_total / (1024**3), 2),
                        "free_gb": round(path_free / (1024**3), 2),
                        "used_percent": round(path_used_percent, 1),
                    }
                except Exception as path_e:
                    logger.exception("操作失败")
                    diagnostic_info[f"{path_name}_error"] = str(path_e)

        return ComponentHealth(
            name="disk",
            status=status,
            message=f"Disk usage: {used_percent:.1f}%",
            details={
                "total_gb": round(total / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "used_percent": round(used_percent, 1),
            },
            diagnostic_info=diagnostic_info,
        )
    except Exception as e:
        logger.exception("操作失败")
        diagnostic_info.update({"error_type": type(e).__name__, "error_details": str(e)})

        return ComponentHealth(
            name="disk",
            status=HealthStatus.DEGRADED,
            message=f"Disk check error: {e!s}",
            diagnostic_info=diagnostic_info,
        )


def check_dependencies() -> ComponentHealth:
    """检查外部依赖服务"""
    diagnostic_info: dict[str, Any] = {}

    try:
        env_vars = ["DJANGO_SECRET_KEY", "DATABASE_PATH", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS"]

        env_status: dict[str, Any] = {}
        for var in env_vars:
            value = os.environ.get(var)
            env_status[var] = {
                "set": value is not None,
                "empty": not bool(value) if value is not None else True,
                "length": len(value) if value else 0,
            }

        diagnostic_info["environment_variables"] = env_status

        important_paths = ["/app/data", "/app/media", "/app/logs", "/app/staticfiles"]

        path_status: dict[str, Any] = {}
        for path in important_paths:
            p = Path(str(path))
            path_status[path] = {
                "exists": p.exists(),
                "is_dir": p.isdir() if p.exists() else False,
                "readable": os.access(str(p), os.R_OK) if p.exists() else False,
                "writable": os.access(str(p), os.W_OK) if p.exists() else False,
            }

        diagnostic_info["important_paths"] = path_status

        from django.apps import apps

        installed_apps = [app.name for app in apps.get_app_configs()]
        diagnostic_info["installed_apps"] = installed_apps
        diagnostic_info["apps_ready"] = apps.ready

        status = HealthStatus.HEALTHY
        issues: list[str] = []

        if not env_status.get("DJANGO_SECRET_KEY", {}).get("set"):
            status = HealthStatus.UNHEALTHY
            issues.append("DJANGO_SECRET_KEY not set")

        missing_paths = [path for path, info in path_status.items() if not info["exists"]]
        if missing_paths:
            status = HealthStatus.DEGRADED if status == HealthStatus.HEALTHY else status
            issues.append(f"Missing paths: {', '.join(missing_paths)}")

        message = "Dependencies OK" if not issues else "; ".join(issues)

        return ComponentHealth(
            name="dependencies",
            status=status,
            message=message,
            diagnostic_info=diagnostic_info,
        )

    except Exception as e:
        logger.exception("操作失败")
        diagnostic_info.update({"error_type": type(e).__name__, "error_details": str(e)})

        return ComponentHealth(
            name="dependencies",
            status=HealthStatus.DEGRADED,
            message=f"Dependencies check error: {e!s}",
            diagnostic_info=diagnostic_info,
        )
