"""Utility functions."""

from __future__ import annotations

from typing import Any

from apps.core.telemetry.time import utc_now_iso

from .common import get_logger


class AutomationMiscLoggerMixin:
    @staticmethod
    def log_admin_operation_start(operation: str, user_id: int | None = None, **kwargs: Any) -> None:
        extra = {
            "action": "admin_operation_start",
            "operation": operation,
            "timestamp": utc_now_iso(),
        }
        if user_id is not None:
            extra["user_id"] = user_id  # type: ignore[assignment]
        extra.update(kwargs)

        get_logger().info(f"开始Admin操作: {operation}", extra=extra)

    @staticmethod
    def log_admin_operation_success(
        operation: str, affected_count: int, processing_time: float, user_id: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "admin_operation_success",
            "success": True,
            "operation": operation,
            "affected_count": affected_count,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)

        get_logger().info(f"Admin操作成功: {operation}", extra=extra)

    @staticmethod
    def log_admin_operation_failed(
        operation: str, error_message: str, processing_time: float, user_id: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "admin_operation_failed",
            "success": False,
            "operation": operation,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)

        get_logger().error(f"Admin操作失败: {operation}", extra=extra)

    @staticmethod
    def log_business_operation(
        operation: str,
        resource_type: str,
        resource_id: int | str | None = None,
        user_id: int | None = None,
        success: bool = True,
        **kwargs: Any,
    ) -> None:
        extra = {
            "action": "business_operation",
            "operation": operation,
            "resource_type": resource_type,
            "success": success,
            "timestamp": utc_now_iso(),
        }
        if resource_id is not None:
            extra["resource_id"] = resource_id
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)

        log_level = get_logger().info if success else get_logger().error
        log_level(f"业务操作: {operation} {resource_type}", extra=extra)

    @staticmethod
    def log_cross_module_call(
        source_module: str, target_module: str, service_name: str, method_name: str, **kwargs: Any
    ) -> None:
        extra = {
            "action": "cross_module_call",
            "source_module": source_module,
            "target_module": target_module,
            "service_name": service_name,
            "method_name": method_name,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().debug(f"跨模块调用: {source_module} -> {target_module}.{service_name}.{method_name}", extra=extra)

    @staticmethod
    def log_fallback_triggered(
        from_method: str,
        to_method: str,
        reason: str,
        error_type: str | None = None,
        credential_id: int | None = None,
        **kwargs: Any,
    ) -> None:
        extra = {
            "action": "fallback_triggered",
            "from_method": from_method,
            "to_method": to_method,
            "reason": reason,
            "timestamp": utc_now_iso(),
        }
        if error_type is not None:
            extra["error_type"] = error_type
        if credential_id is not None:
            extra["credential_id"] = credential_id  # type: ignore[assignment]
        extra.update(kwargs)

        get_logger().warning(f"降级触发: {from_method} -> {to_method}, 原因: {reason}", extra=extra)

    @staticmethod
    def log_api_error_detail(
        api_name: str,
        error_type: str,
        error_message: str,
        stack_trace: str | None = None,
        request_params: dict[str, Any] | None = None,
        response_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        extra = {
            "action": "api_error_detail",
            "api_name": api_name,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": utc_now_iso(),
        }
        if stack_trace is not None:
            extra["stack_trace"] = stack_trace
        if request_params is not None:
            safe_params = ({},)  # type: ignore[var-annotated]
            extra["request_params"] = safe_params  # type: ignore[assignment]
        if response_data is not None:
            extra["response_data"] = response_data  # type: ignore[assignment]
        extra.update(kwargs)

        get_logger().error(f"API错误详情: {api_name} - {error_type}: {error_message}", extra=extra)
