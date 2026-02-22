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
