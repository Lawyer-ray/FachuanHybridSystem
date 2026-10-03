"""性能监控、通用业务日志 Mixin"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ApiLoggingMixin:
    """性能监控、通用业务相关日志方法"""

    @staticmethod
    def log_performance_metrics_collection_start(metric_type: str, **kwargs: Any) -> None:
        """记录性能指标收集开始"""
        extra: dict[str, Any] = {
            "action": "performance_metrics_collection_start",
            "metric_type": metric_type,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.debug("开始收集%s性能指标", metric_type, extra=extra)

    @staticmethod
    def log_performance_metrics_collection_success(
        metric_type: str, metrics_count: int, collection_time: float, **kwargs: Any
    ) -> None:
        """记录性能指标收集成功"""
        extra: dict[str, Any] = {
            "action": "performance_metrics_collection_success",
            "success": True,
            "metric_type": metric_type,
            "metrics_count": metrics_count,
            "collection_time": collection_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.debug("%s性能指标收集成功", metric_type, extra=extra)

    @staticmethod
    def log_business_operation(
        operation: str,
        resource_type: str,
        resource_id: int | str | None = None,
        user_id: int | None = None,
        success: bool = True,
        **kwargs: Any,
    ) -> None:
        """记录通用业务操作"""
        extra: dict[str, Any] = {
            "action": "business_operation",
            "operation": operation,
            "resource_type": resource_type,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        if resource_id is not None:
            extra["resource_id"] = resource_id
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        log_level = logger.info if success else logger.error
        log_level(f"业务操作: {operation} {resource_type}", extra=extra)
