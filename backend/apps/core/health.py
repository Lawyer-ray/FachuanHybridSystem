"""
健康检查模块
提供系统健康状态检查功能
"""
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from django.db import connection
from django.core.cache import cache


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
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """系统健康状态"""
    status: HealthStatus
    version: str
    uptime_seconds: float
    components: List[ComponentHealth] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2) if c.latency_ms else None,
                    "message": c.message,
                    "details": c.details,
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
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Database connection OK",
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
            )

    @staticmethod
    def check_cache() -> ComponentHealth:
        """检查缓存连接"""
        start = time.time()
        test_key = "_health_check_"
        test_value = "ok"

        try:
            # 写入测试
            cache.set(test_key, test_value, 10)

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
                )
            else:
                return ComponentHealth(
                    name="cache",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message="Cache read/write mismatch",
                )
        except Exception as e:
            return ComponentHealth(
                name="cache",
                status=HealthStatus.DEGRADED,  # 缓存不可用不影响核心功能
                message=f"Cache error: {str(e)}",
            )

    @staticmethod
    def check_disk_space() -> ComponentHealth:
        """检查磁盘空间"""
        import os
        from django.conf import settings

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

            return ComponentHealth(
                name="disk",
                status=status,
                message=f"Disk usage: {used_percent:.1f}%",
                details={
                    "total_gb": round(total / (1024**3), 2),
                    "free_gb": round(free / (1024**3), 2),
                    "used_percent": round(used_percent, 1),
                },
            )
        except Exception as e:
            return ComponentHealth(
                name="disk",
                status=HealthStatus.DEGRADED,
                message=f"Disk check error: {str(e)}",
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
        from django.conf import settings

        components = [
            cls.check_database(),
            cls.check_cache(),
        ]

        if include_details:
            components.append(cls.check_disk_space())

        # 计算整体状态
        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        # 优先使用 APP_VERSION（Docker 部署），回退到 API_VERSION
        version = getattr(settings, "APP_VERSION", None) or getattr(settings, "API_VERSION", "1.0.0")

        return SystemHealth(
            status=overall_status,
            version=version,
            uptime_seconds=time.time() - _start_time,
            components=components,
        )

    @classmethod
    def liveness_check(cls) -> Dict[str, str]:
        """
        存活检查（Kubernetes liveness probe）
        仅检查应用是否运行
        """
        return {"status": "ok"}

    @classmethod
    def readiness_check(cls) -> Dict[str, Any]:
        """
        就绪检查（Kubernetes readiness probe）
        检查应用是否可以接收流量
        """
        db_health = cls.check_database()

        if db_health.status == HealthStatus.UNHEALTHY:
            return {
                "status": "not_ready",
                "reason": db_health.message,
            }

        return {"status": "ready"}
