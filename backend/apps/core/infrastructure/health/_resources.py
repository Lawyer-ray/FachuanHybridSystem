"""系统资源检查（CPU、内存、psutil）"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import Any

import psutil

from ._models import ComponentHealth, HealthStatus

logger = logging.getLogger(__name__)

__all__ = ["check_system_resources"]

# 导入资源监控模块
try:
    from apps.core.infrastructure.resource_monitor import get_resource_status, get_resource_usage, resource_monitor

    RESOURCE_MONITOR_AVAILABLE = True
except ImportError:
    RESOURCE_MONITOR_AVAILABLE = False


def check_system_resources() -> ComponentHealth:
    """
    检查系统资源使用情况
    Requirements: 4.1, 4.2, 4.3, 4.4
    """
    diagnostic_info: dict[str, Any] = {}

    try:
        if RESOURCE_MONITOR_AVAILABLE:
            result = _check_via_resource_monitor(diagnostic_info)
            if result is not None:
                return result

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


def _check_via_resource_monitor(diagnostic_info: dict[str, Any]) -> ComponentHealth | None:
    """使用资源监控模块检查，返回 None 表示数据不可用"""
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

    status, issues = _evaluate_resource_status(cpu_percent, memory.percent, load_avg, cpu_count or 1)
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
    cpu_percent: float,
    memory_percent: float,
    load_avg: tuple[float, float, float] | None,
    cpu_count: int,
) -> tuple[HealthStatus, list[str]]:
    """评估系统资源状态"""
    status = HealthStatus.HEALTHY
    issues: list[str] = []

    if cpu_percent > 90:
        status = HealthStatus.DEGRADED
        issues.append(f"High CPU usage: {cpu_percent}%")

    if memory_percent > 90:
        status = HealthStatus.UNHEALTHY
        issues.append(f"High memory usage: {memory_percent}%")
    elif memory_percent > 80:
        if status == HealthStatus.HEALTHY:
            status = HealthStatus.DEGRADED
        issues.append(f"Elevated memory usage: {memory_percent}%")

    if load_avg and load_avg[0] > cpu_count * 2:
        if status == HealthStatus.HEALTHY:
            status = HealthStatus.DEGRADED
        issues.append(f"High system load: {load_avg[0]:.2f}")

    return status, issues
