"""
资源监控模块 - 兼容层

此文件为向后兼容保留,实际实现已移至 infrastructure/resource_monitor.py
新代码建议使用: from apps.core.infrastructure import resource_monitor, get_resource_status
"""

import warnings

from .infrastructure.resource_monitor import (
    ResourceMonitor,
    ResourceThresholds,
    ResourceUsage,
    get_resource_status,
    get_resource_usage,
    resource_monitor,
    start_resource_monitoring,
    stop_resource_monitoring,
)

warnings.warn(
    "从 apps.core.resource_monitor 导入已废弃,请使用 apps.core.infrastructure.resource_monitor",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = [
    "ResourceMonitor",
    "ResourceThresholds",
    "ResourceUsage",
    "get_resource_status",
    "get_resource_usage",
    "resource_monitor",
    "start_resource_monitoring",
    "stop_resource_monitoring",
]
