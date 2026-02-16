# ============================================================
# 法穿案件管理系统 - 资源监控和保护机制
# ============================================================
# Requirements: 4.1, 4.2, 4.3, 4.4
# 实现资源监控、动态分配和保护机制
# ============================================================

"""Module for resource monitor."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - resource monitoring will be limited")


@dataclass
class ResourceUsage:
    """资源使用情况数据模型"""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    timestamp: datetime


@dataclass
class ResourceThresholds:
    """资源阈值配置"""

    memory_warning: float = 80.0
    memory_critical: float = 90.0
    cpu_warning: float = 80.0
    disk_warning: float = 85.0
    disk_critical: float = 95.0
    auto_restart_memory: float = 95.0


class ResourceMonitor:
    """
    资源监控和保护机制

    Requirements:
    - 4.1: 系统负载较低时使用最小必要资源
    - 4.2: 系统负载较高时扩展到配置的资源上限
    - 4.3: 内存使用过高时自动重启相关服务防止OOM
    - 4.4: 磁盘空间不足时提供清晰的警告信息
    """

    def __init__(self) -> None:
        self.thresholds = self._load_thresholds()
        self.monitoring_enabled = self._get_bool_env("RESOURCE_MONITORING_ENABLED", True)
        self.auto_restart_enabled = self._get_bool_env("AUTO_RESTART_ON_HIGH_MEMORY", True)
        self.restart_cooldown = int(os.getenv("RESTART_COOLDOWN_SECONDS", "300"))

        self._last_restart_time: datetime | None = None
        self._monitoring_thread: threading.Thread | None = None
        self._stop_monitoring = threading.Event()

        if not PSUTIL_AVAILABLE:
            logger.warning("Resource monitoring disabled - psutil not available")
            self.monitoring_enabled = False

    def _load_thresholds(self) -> ResourceThresholds:
        """从环境变量加载资源阈值配置"""
        return ResourceThresholds(
            memory_warning=float(os.getenv("MEMORY_WARNING_THRESHOLD", "80")),
            memory_critical=float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "90")),
            cpu_warning=float(os.getenv("CPU_WARNING_THRESHOLD", "80")),
            disk_warning=float(os.getenv("DISK_WARNING_THRESHOLD", "85")),
            disk_critical=float(os.getenv("DISK_CRITICAL_THRESHOLD", "95")),
            auto_restart_memory=float(os.getenv("AUTO_RESTART_MEMORY_THRESHOLD", "95")),
        )

    def _get_bool_env(self, key: str, default: bool) -> bool:
        """获取布尔类型环境变量"""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    def get_current_usage(self) -> ResourceUsage | None:
        """
        获取当前资源使用情况
        Requirements: 4.1, 4.2 - 监控系统负载
        """
        if not PSUTIL_AVAILABLE:
            return None

        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)

            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / 1024 / 1024
            memory_total_mb = memory.total / 1024 / 1024

            # 磁盘使用情况
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            disk_used_gb = disk.used / 1024 / 1024 / 1024
            disk_total_gb = disk.total / 1024 / 1024 / 1024

            return ResourceUsage(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                disk_percent=disk_percent,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")
            return None

    def check_resource_health(self) -> dict[str, Any]:
        """
        检查资源健康状态
        Requirements: 4.3, 4.4 - 资源保护和警告
        """
        usage = self.get_current_usage()
        if not usage:
            return {"status": "unknown", "message": "Resource monitoring unavailable"}

        issues = []
        status = "healthy"

        # 检查内存使用
        if usage.memory_percent >= self.thresholds.memory_critical:
            issues.append(f"Critical: Memory usage {usage.memory_percent:.1f}% (>{self.thresholds.memory_critical}%)")
            status = "critical"
        elif usage.memory_percent >= self.thresholds.memory_warning:
            issues.append(f"Warning: Memory usage {usage.memory_percent:.1f}% (>{self.thresholds.memory_warning}%)")
            if status == "healthy":
                status = "warning"

        # 检查CPU使用
        if usage.cpu_percent >= self.thresholds.cpu_warning:
            issues.append(f"Warning: CPU usage {usage.cpu_percent:.1f}% (>{self.thresholds.cpu_warning}%)")
            if status == "healthy":
                status = "warning"

        # 检查磁盘使用
        if usage.disk_percent >= self.thresholds.disk_critical:
            issues.append(f"Critical: Disk usage {usage.disk_percent:.1f}% (>{self.thresholds.disk_critical}%)")
            status = "critical"
        elif usage.disk_percent >= self.thresholds.disk_warning:
            issues.append(f"Warning: Disk usage {usage.disk_percent:.1f}% (>{self.thresholds.disk_warning}%)")
            if status == "healthy":
                status = "warning"

        details: dict[str, Any] = {
            "cpu_percent": usage.cpu_percent,
            "memory_percent": usage.memory_percent,
            "memory_used_mb": usage.memory_used_mb,
            "disk_percent": usage.disk_percent,
            "disk_used_gb": usage.disk_used_gb,
            "timestamp": usage.timestamp.isoformat(),
        }

        return {
            "status": status,
            "message": "; ".join(issues) if issues else "All resources within normal limits",
            "details": details,
        }

    def should_trigger_restart(self) -> tuple[bool, str]:
        """
        检查是否应该触发自动重启
        Requirements: 4.3 - 内存使用过高时自动重启相关服务防止OOM
        """
        if not self.auto_restart_enabled:
            return False, "Auto restart disabled"

        # 检查冷却时间
        if self._last_restart_time:
            cooldown_end = self._last_restart_time + timedelta(seconds=self.restart_cooldown)
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).total_seconds()
                return False, f"Restart cooldown active ({remaining:.0f}s remaining)"

        usage = self.get_current_usage()
        if not usage:
            return False, "Resource monitoring unavailable"

        if usage.memory_percent >= self.thresholds.auto_restart_memory:
            return (
                True,
                f"Memory usage {usage.memory_percent:.1f}% exceeds "
                f"restart threshold {self.thresholds.auto_restart_memory}%",
            )

        return False, "Memory usage within acceptable limits"

    def record_restart(self) -> None:
        """记录重启时间"""
        self._last_restart_time = datetime.now()
        logger.info(f"Recorded restart at {self._last_restart_time}")

    def get_resource_recommendations(self) -> dict[str, Any]:
        """
        获取资源优化建议
        Requirements: 4.1, 4.2 - 动态资源分配建议
        """
        usage = self.get_current_usage()
        if not usage:
            return {"message": "Resource monitoring unavailable"}

        recommendations = []

        # CPU建议
        if usage.cpu_percent < 30:
            recommendations.append("CPU usage is low - consider reducing worker processes")
        elif usage.cpu_percent > 80:
            recommendations.append("CPU usage is high - consider increasing worker processes or CPU limits")

        # 内存建议
        if usage.memory_percent < 40:
            recommendations.append("Memory usage is low - current allocation may be excessive")
        elif usage.memory_percent > 80:
            recommendations.append("Memory usage is high - consider increasing memory limits or optimizing application")

        # 磁盘建议
        if usage.disk_percent > 85:
            recommendations.append("Disk usage is high - consider cleanup or increasing disk space")

        current_usage: dict[str, str] = {
            "cpu": f"{usage.cpu_percent:.1f}%",
            "memory": f"{usage.memory_percent:.1f}%",
            "disk": f"{usage.disk_percent:.1f}%",
        }

        return {
            "recommendations": recommendations,
            "current_usage": current_usage,
        }

    def start_monitoring(self, interval: int = 60) -> None:
        """
        启动后台资源监控
        Requirements: 4.3, 4.4 - 持续监控和保护
        """
        if not self.monitoring_enabled:
            logger.info("Resource monitoring disabled")
            return

        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Resource monitoring already running")
            return

        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop, args=(interval,), daemon=True, name="ResourceMonitor"
        )
        self._monitoring_thread.start()
        logger.info(f"Started resource monitoring with {interval}s interval")

    def stop_monitoring(self) -> None:
        """停止资源监控"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._stop_monitoring.set()
            self._monitoring_thread.join(timeout=5)
            logger.info("Stopped resource monitoring")

    def _monitoring_loop(self, interval: int) -> None:
        """资源监控循环"""
        while not self._stop_monitoring.wait(interval):
            try:
                health = self.check_resource_health()

                if health["status"] == "critical":
                    logger.error(f"Resource critical: {health['message']}")
                elif health["status"] == "warning":
                    logger.warning(f"Resource warning: {health['message']}")

                # 检查是否需要自动重启
                should_restart, reason = self.should_trigger_restart()
                if should_restart:
                    logger.critical(f"Auto restart triggered: {reason}")
                    # 这里可以集成实际的重启逻辑
                    # 例如:发送信号给容器管理器或记录重启请求
                    self.record_restart()

            except Exception as e:
                logger.error(f"Error in resource monitoring loop: {e}")


# 全局资源监控实例
resource_monitor = ResourceMonitor()


def get_resource_status() -> dict[str, Any]:
    """获取资源状态的便捷函数"""
    return resource_monitor.check_resource_health()


def get_resource_usage() -> ResourceUsage | None:
    """获取资源使用情况的便捷函数"""
    return resource_monitor.get_current_usage()


def start_resource_monitoring() -> None:
    """启动资源监控的便捷函数"""
    resource_monitor.start_monitoring()


def stop_resource_monitoring() -> None:
    """停止资源监控的便捷函数"""
    resource_monitor.stop_monitoring()
