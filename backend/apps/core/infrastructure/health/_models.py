"""健康检查数据模型"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["HealthStatus", "ComponentHealth", "SystemHealth"]


class HealthStatus(str, Enum):
    """健康状态枚举"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# 安全审计（2026-10-19）：/api/v1/health 无认证暴露，曾泄露 Redis 连接串与 DB 拓扑。
# include_details=False 时组件 message 一律用下面的固定短句替换，不带异常原文、
# 连接串或主机名；原始异常与 diagnostic_info 仅内部排障（admin 详情端点/日志）使用。
_PUBLIC_MESSAGES: dict[str, dict[str, str]] = {
    "database": {
        HealthStatus.HEALTHY.value: "数据库正常",
        HealthStatus.DEGRADED.value: "数据库降级",
        HealthStatus.UNHEALTHY.value: "数据库不可用",
    },
    "cache": {
        HealthStatus.HEALTHY.value: "缓存正常",
        HealthStatus.DEGRADED.value: "缓存不可用",
        HealthStatus.UNHEALTHY.value: "缓存不可用",
    },
    "disk": {
        HealthStatus.HEALTHY.value: "磁盘正常",
        HealthStatus.DEGRADED.value: "磁盘空间紧张",
        HealthStatus.UNHEALTHY.value: "磁盘空间不足",
    },
    "system_resources": {
        HealthStatus.HEALTHY.value: "系统资源正常",
        HealthStatus.DEGRADED.value: "系统资源紧张",
        HealthStatus.UNHEALTHY.value: "系统资源异常",
    },
    "dependencies": {
        HealthStatus.HEALTHY.value: "依赖正常",
        HealthStatus.DEGRADED.value: "依赖异常",
        HealthStatus.UNHEALTHY.value: "依赖缺失",
    },
}
_DEFAULT_PUBLIC_MESSAGES: dict[str, str] = {
    HealthStatus.HEALTHY.value: "正常",
    HealthStatus.DEGRADED.value: "降级",
    HealthStatus.UNHEALTHY.value: "不可用",
}


def _public_message(name: str, status: HealthStatus) -> str:
    """对外（无认证）健康输出的人话短句，不含内部异常与连接信息。"""
    return _PUBLIC_MESSAGES.get(name, _DEFAULT_PUBLIC_MESSAGES)[status.value]


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

    def to_dict(self, include_details: bool = False) -> dict[str, Any]:
        # 安全审计（2026-10-19）：默认（无认证调用方）只回各组件 status/latency_ms
        # 与人话短句 message；diagnostic_info、details、system_info 与原始异常
        # message 均不外发。内部用途（admin /health/detail）显式传
        # include_details=True 保留完整排障能力。
        if include_details:
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
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2) if c.latency_ms else None,
                    "message": _public_message(c.name, c.status),
                }
                for c in self.components
            ],
        }


# 记录启动时间
_start_time = time.time()
