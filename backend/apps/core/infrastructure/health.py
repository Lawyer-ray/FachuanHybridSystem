"""Module for health."""

from __future__ import annotations

"""
健康检查模块
提供系统健康状态检查功能
Requirements: 3.1, 3.2, 3.3, 3.4, 4.3, 4.4
"""

import contextlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import psutil
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.core.path import Path

from .cache import CacheTimeout

logger = logging.getLogger(__name__)

# 导入资源监控模块(使用相对导入)
try:
    from .resource_monitor import get_resource_status, get_resource_usage, resource_monitor

    RESOURCE_MONITOR_AVAILABLE = True
except ImportError:
    RESOURCE_MONITOR_AVAILABLE = False


class HealthStatus(str, Enum):
    """健康状态枚举"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """组件健康状态"""

    name: str
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    diagnostic_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """系统健康状态"""

    status: HealthStatus
    version: str
    uptime_seconds: float
    components: list[ComponentHealth] = field(default_factory=list)
    system_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "system_info": self.system_info,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2) if c.latency_ms else None,
                    "message": c.message,
                    "details": c.details,
                    "diagnostic_info": c.diagnostic_info,
                }
                for c in self.components
            ],
        }


# 记录启动时间
_start_time = time.time()


class HealthChecker:
    """健康检查器"""

    @staticmethod
    def check_database() -> ComponentHealth:
        """检查数据库连接"""
        start = time.time()
        diagnostic_info = {}

        try:
            # 基础连接测试
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

            latency = (time.time() - start) * 1000

            # 收集数据库诊断信息
            try:
                db_path = getattr(settings, "DATABASES", {}).get("default", {}).get("NAME", "")
                if db_path:
                    db_file = Path(str(db_path))
                else:
                    db_file = None
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

                # 数据库连接池信息
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
            # 静默处理:文件操作失败不影响主流程
            # 收集失败诊断信息
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

    @staticmethod
    def check_cache() -> ComponentHealth:
        """检查缓存连接"""
        start = time.time()
        test_key = "_health_check_"
        test_value = "ok"
        diagnostic_info = {}

        try:
            # 收集缓存配置信息
            cache_config = getattr(settings, "CACHES", {}).get("default", {})
            diagnostic_info.update(
                {
                    "cache_backend": cache_config.get("BACKEND", "unknown"),
                    "cache_location": cache_config.get("LOCATION", "unknown"),
                }
            )

            # 写入测试
            cache.set(test_key, test_value, CacheTimeout.get_short())

            # 读取测试
            result = cache.get(test_key)

            # 删除测试
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
                diagnostic_info["read_write_test"] = {
                    "expected": test_value,
                    "actual": result,
                }
                return ComponentHealth(
                    name="cache",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message="Cache read/write mismatch",
                    diagnostic_info=diagnostic_info,
                )
        except Exception as e:
            logger.exception("操作失败")
            diagnostic_info.update(
                {
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                }
            )

            return ComponentHealth(
                name="cache",
                status=HealthStatus.DEGRADED,  # 缓存不可用不影响核心功能
                message=f"Cache error: {e!s}",
                diagnostic_info=diagnostic_info,
            )

    @staticmethod
    def check_disk_space() -> ComponentHealth:
        """检查磁盘空间"""
        diagnostic_info = {}

        try:
            media_root = getattr(settings, "MEDIA_ROOT", "/tmp")
            stat = os.statvfs(str(media_root))

            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used_percent = ((total - free) / total) * 100 if total > 0 else 0

            status = HealthStatus.HEALTHY
            if used_percent > 90:
                status = HealthStatus.UNHEALTHY
            elif used_percent > 80:
                status = HealthStatus.DEGRADED

            # 收集详细磁盘信息
            diagnostic_info.update(
                {
                    "media_root": str(media_root),
                    "filesystem_type": "unknown",  # 可以通过其他方式获取
                    "total_inodes": stat.f_files,
                    "free_inodes": stat.f_ffree,
                    "block_size": stat.f_frsize,
                }
            )

            # 检查其他重要目录
            important_paths = [
                (
                    "database_dir",
                    str(Path(str(getattr(settings, "DATABASES", {}).get("default", {}).get("NAME", "/tmp"))).parent),
                ),
                ("logs_dir", "/app/logs"),
                ("static_dir", getattr(settings, "STATIC_ROOT", "/tmp")),
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
            diagnostic_info.update(
                {
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                }
            )

            return ComponentHealth(
                name="disk",
                status=HealthStatus.DEGRADED,
                message=f"Disk check error: {e!s}",
                diagnostic_info=diagnostic_info,
            )

    @staticmethod
    def check_system_resources() -> ComponentHealth:
        """
        检查系统资源使用情况
        Requirements: 4.1, 4.2, 4.3, 4.4 - 集成资源监控和保护机制
        """
        diagnostic_info: dict[str, Any] = {}

        try:
            # 优先使用资源监控模块
            if RESOURCE_MONITOR_AVAILABLE:
                result = _check_via_resource_monitor(diagnostic_info)
                if result is not None:
                    return result

            # 回退到原有的psutil检查
            return _check_via_psutil(diagnostic_info)

        except Exception as e:
            logger.exception("操作失败")
            diagnostic_info.update(
                {
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                    "resource_monitor_enabled": RESOURCE_MONITOR_AVAILABLE,
                }
            )

            return ComponentHealth(
                name="system_resources",
                status=HealthStatus.DEGRADED,
                message=f"System resources check error: {e!s}",
                diagnostic_info=diagnostic_info,
            )

    @staticmethod
    def check_dependencies() -> ComponentHealth:
        """检查外部依赖服务"""
        diagnostic_info = {}

        try:
            # 检查重要的环境变量
            env_vars = [
                "DJANGO_SECRET_KEY",
                "DATABASE_PATH",
                "DJANGO_DEBUG",
                "DJANGO_ALLOWED_HOSTS",
            ]

            env_status = {}
            for var in env_vars:
                value = os.environ.get(var)
                env_status[var] = {
                    "set": value is not None,
                    "empty": not bool(value) if value is not None else True,
                    "length": len(value) if value else 0,
                }

            diagnostic_info["environment_variables"] = env_status

            # 检查关键文件和目录
            important_paths = [
                "/app/data",
                "/app/media",
                "/app/logs",
                "/app/staticfiles",
            ]

            path_status = {}
            for path in important_paths:
                p = Path(str(path))
                path_status[path] = {
                    "exists": p.exists(),
                    "is_dir": p.isdir() if p.exists() else False,
                    "readable": os.access(str(p), os.R_OK) if p.exists() else False,
                    "writable": os.access(str(p), os.W_OK) if p.exists() else False,
                }

            diagnostic_info["important_paths"] = path_status

            # 检查 Django 应用状态
            from django.apps import apps

            installed_apps = [app.name for app in apps.get_app_configs()]
            diagnostic_info["installed_apps"] = installed_apps  # type: ignore[assignment]
            diagnostic_info["apps_ready"] = apps.ready  # type: ignore[assignment]

            # 判断依赖状态
            status = HealthStatus.HEALTHY
            issues: list[str] = []

            # 检查关键环境变量
            if not env_status.get("DJANGO_SECRET_KEY", {}).get("set"):
                status = HealthStatus.UNHEALTHY
                issues.append("DJANGO_SECRET_KEY not set")

            # 检查关键路径
            missing_paths = [path for path, info in path_status.items() if not info["exists"]]
            if missing_paths:
                status = HealthStatus.DEGRADED if status == HealthStatus.HEALTHY else status
                issues.append(f"Missing paths: {', '.join(missing_paths)}")

            message = "Dependencies OK"
            if issues:
                message = "; ".join(issues)

            return ComponentHealth(
                name="dependencies",
                status=status,
                message=message,
                diagnostic_info=diagnostic_info,
            )

        except Exception as e:
            logger.exception("操作失败")
            diagnostic_info.update(
                {
                    "error_type": type(e).__name__,  # type: ignore[dict-item]
                    "error_details": str(e),  # type: ignore[dict-item]
                }
            )

            return ComponentHealth(
                name="dependencies",
                status=HealthStatus.DEGRADED,
                message=f"Dependencies check error: {e!s}",
                diagnostic_info=diagnostic_info,
            )

    @classmethod
    def get_system_health(cls, include_details: bool = False) -> SystemHealth:
        """
        获取系统健康状态

        Args:
            include_details: 是否包含详细信息

        Returns:
            系统健康状态
        """
        components = [
            cls.check_database(),
            cls.check_cache(),
        ]

        if include_details:
            components.extend(
                [
                    cls.check_disk_space(),
                    cls.check_system_resources(),
                    cls.check_dependencies(),
                ]
            )

        # 计算整体状态
        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        # 收集系统信息
        system_info = {}
        if include_details:
            try:
                import sys

                system_info.update(
                    {
                        "hostname": os.uname().nodename,
                        "platform": os.uname().sysname,
                        "python_version": sys.version.split()[0],
                        "django_version": getattr(settings, "DJANGO_VERSION", "unknown"),
                        "service_name": os.environ.get("SERVICE_NAME", "backend"),
                        "service_role": os.environ.get("SERVICE_ROLE", "web"),
                        "environment_type": os.environ.get("ENVIRONMENT_TYPE", "production"),
                    }
                )
            except Exception as e:
                logger.exception("操作失败")
                system_info["collection_error"] = str(e)

        # 优先使用 APP_VERSION(Docker 部署),回退到 API_VERSION
        version = os.environ.get("APP_VERSION") or str(getattr(settings, "API_VERSION", "1.0.0"))

        return SystemHealth(
            status=overall_status,
            version=version,
            uptime_seconds=time.time() - _start_time,
            components=components,
            system_info=system_info,
        )

    @classmethod
    def liveness_check(cls) -> dict[str, str]:
        """
        存活检查(Kubernetes liveness probe)
        仅检查应用是否运行
        """
        return {"status": "ok", "timestamp": str(time.time())}

    @classmethod
    def readiness_check(cls) -> dict[str, Any]:
        """
        就绪检查(Kubernetes readiness probe)
        检查应用是否可以接收流量
        """
        db_health = cls.check_database()
        cache_health = cls.check_cache()
        llm_health_value = "unknown"
        llm_error = None
        llm_required = False

        try:
            from apps.core.llm.warmup import get_llm_warmup_state

            llm_state = get_llm_warmup_state()
            llm_ok = bool(llm_state.get("ok"))
            llm_ts = llm_state.get("timestamp")
            llm_error = llm_state.get("error")
            llm_required = bool(getattr(settings, "LITIGATION_USE_AGENT_MODE", False)) or (
                (os.environ.get("DJANGO_LLM_READY_REQUIRED", "") or "").lower().strip() in ("true", "1", "yes")
            )
            if llm_ts is None:
                llm_health_value = "unknown"
            else:
                llm_health_value = "healthy" if llm_ok else "unhealthy"
        except Exception as e:
            logger.exception("操作失败")
            llm_health_value = "unknown"
            llm_error = str(e)

        if db_health.status == HealthStatus.UNHEALTHY:
            return {
                "status": "not_ready",
                "reason": db_health.message,
                "component": "database",
                "timestamp": time.time(),
            }

        if llm_required and llm_health_value == "unhealthy":
            return {
                "status": "not_ready",
                "reason": f"LLM warmup failed: {llm_error or 'unknown'}",
                "component": "llm_config",
                "timestamp": time.time(),
            }

        # 缓存降级不影响就绪状态,但记录信息
        ready_info = {
            "status": "ready",
            "timestamp": time.time(),
            "components": {
                "database": db_health.status.value,
                "cache": cache_health.status.value,
                "llm_config": llm_health_value,
            },
        }

        if cache_health.status != HealthStatus.HEALTHY:
            ready_info["warnings"] = [f"Cache {cache_health.status.value}: {cache_health.message}"]
        if (not llm_required) and llm_health_value == "unhealthy":
            warnings_obj = ready_info.get("warnings")
            if isinstance(warnings_obj, list):
                warnings = list(warnings_obj)
            else:
                warnings: list[Any] = []  # type: ignore[no-redef]
            warnings.append(f"LLM warmup failed: {llm_error or 'unknown'}")
            ready_info["warnings"] = warnings
        if llm_health_value == "unknown" and llm_required:
            warnings_obj = ready_info.get("warnings")
            if isinstance(warnings_obj, list):
                warnings = list(warnings_obj)
            else:
                warnings: list[Any] = []  # type: ignore[no-redef]
            warnings.append("LLM warmup not executed yet")
            ready_info["warnings"] = warnings

        return ready_info


def _check_via_resource_monitor(diagnostic_info: dict[str, Any]) -> ComponentHealth | None:
    """使用资源监控模块检查系统资源,返回 None 表示数据不可用"""
    resource_status = get_resource_status()
    resource_usage = get_resource_usage()

    if not (resource_status and resource_usage):
        return None

    status_mapping = {
        "healthy": HealthStatus.HEALTHY,
        "warning": HealthStatus.DEGRADED,
        "critical": HealthStatus.UNHEALTHY,
        "unknown": HealthStatus.DEGRADED,
    }

    status = status_mapping.get(resource_status["status"], HealthStatus.DEGRADED)

    diagnostic_info.update(
        {
            "resource_monitor_enabled": True,
            "monitoring_details": resource_status.get("details", {}),
            "auto_restart_enabled": resource_monitor.auto_restart_enabled,
            "restart_cooldown_seconds": resource_monitor.restart_cooldown,
        }
    )

    should_restart, restart_reason = resource_monitor.should_trigger_restart()
    if should_restart:
        diagnostic_info["auto_restart_pending"] = {"reason": restart_reason, "timestamp": time.time()}

    recommendations = resource_monitor.get_resource_recommendations()
    if recommendations.get("recommendations"):
        diagnostic_info["optimization_recommendations"] = recommendations

    return ComponentHealth(
        name="system_resources",
        status=status,
        message=resource_status["message"],
        details={
            "cpu_percent": resource_usage.cpu_percent,
            "memory_percent": resource_usage.memory_percent,
            "disk_percent": resource_usage.disk_percent,
            "memory_used_mb": resource_usage.memory_used_mb,
            "disk_used_gb": resource_usage.disk_used_gb,
        },
        diagnostic_info=diagnostic_info,
    )


def _check_via_psutil(diagnostic_info: dict[str, Any]) -> ComponentHealth:
    """使用 psutil 检查系统资源"""
    diagnostic_info["resource_monitor_enabled"] = False

    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    memory = psutil.virtual_memory()

    current_process = psutil.Process()
    diagnostic_info.update(
        {
            "cpu_count": cpu_count,
            "cpu_percent": cpu_percent,
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_available_gb": round(memory.available / (1024**3), 2),
            "memory_used_percent": memory.percent,
            "process_info": {
                "pid": current_process.pid,
                "cpu_percent": current_process.cpu_percent(),
                "memory_percent": current_process.memory_percent(),
                "memory_info_mb": round(current_process.memory_info().rss / (1024 * 1024), 2),
                "num_threads": current_process.num_threads(),
                "create_time": time.ctime(current_process.create_time()),
            },
        }
    )

    load_avg = None
    with contextlib.suppress(OSError, AttributeError):
        load_avg = os.getloadavg()

    diagnostic_info["load_average"] = list(load_avg) if load_avg else None

    status, issues = _evaluate_resource_status(cpu_percent, memory.percent, load_avg, cpu_count)
    message = "; ".join(issues) if issues else "System resources OK"

    return ComponentHealth(
        name="system_resources",
        status=status,
        message=message,
        details={
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "load_average": load_avg[0] if load_avg else None,
        },
        diagnostic_info=diagnostic_info,
    )


def _evaluate_resource_status(
    cpu_percent: float, memory_percent: float, load_avg: tuple[float, float, float] | None, cpu_count: int
) -> tuple[HealthStatus, list[str]]:
    """评估系统资源状态"""
    status = HealthStatus.HEALTHY
    issues: list[str] = []

    if cpu_percent > 90:
        status = HealthStatus.DEGRADED
        issues.append(f"High CPU usage: {cpu_percent}%")

    if memory_percent > 90:
        status = HealthStatus.UNHEALTHY if status != HealthStatus.UNHEALTHY else status
        issues.append(f"High memory usage: {memory_percent}%")
    elif memory_percent > 80:
        status = HealthStatus.DEGRADED if status == HealthStatus.HEALTHY else status
        issues.append(f"Elevated memory usage: {memory_percent}%")

    if load_avg and load_avg[0] > cpu_count * 2:
        status = HealthStatus.DEGRADED if status == HealthStatus.HEALTHY else status
        issues.append(f"High system load: {load_avg[0]:.2f}")

    return status, issues
