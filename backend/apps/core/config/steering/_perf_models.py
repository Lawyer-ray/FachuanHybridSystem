"""
性能监控数据模型

定义性能监控相关的数据类、枚举和阈值配置。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertLevel(Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """性能指标"""

    name: str
    value: float
    unit: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAlert:
    """性能告警"""

    level: AlertLevel
    message: str
    metric_name: str
    threshold: float
    actual_value: float
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadingPerformanceData:
    """加载性能数据"""

    spec_path: str
    start_time: float
    end_time: float
    duration_ms: float
    success: bool
    error_message: str | None = None
    cache_hit: bool = False
    file_size_bytes: int = 0
    memory_usage_mb: float = 0.0


class PerformanceThresholds:
    """性能阈值配置"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.load_time_warning_ms = config.get("load_time_warning_ms", 500.0)
        self.load_time_error_ms = config.get("load_time_error_ms", 2000.0)
        self.load_time_critical_ms = config.get("load_time_critical_ms", 5000.0)

        self.memory_usage_warning_mb = config.get("memory_usage_warning_mb", 100.0)
        self.memory_usage_error_mb = config.get("memory_usage_error_mb", 500.0)
        self.memory_usage_critical_mb = config.get("memory_usage_critical_mb", 1000.0)

        self.cache_hit_rate_warning = config.get("cache_hit_rate_warning", 0.7)
        self.cache_hit_rate_error = config.get("cache_hit_rate_error", 0.5)

        self.concurrent_loads_warning = config.get("concurrent_loads_warning", 10)
        self.concurrent_loads_error = config.get("concurrent_loads_error", 20)
