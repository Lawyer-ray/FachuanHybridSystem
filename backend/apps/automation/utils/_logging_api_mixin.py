"""性能监控、Admin操作、通用业务、文书API相关日志 Mixin"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ApiLoggingMixin:
    """性能监控、Admin操作、通用业务、文书API相关日志方法"""

    @staticmethod
    def log_performance_metrics_collection_start(metric_type: str, **kwargs: Any) -> None:
        """记录性能指标收集开始"""
        extra: dict[str, Any] = {
            "action": "performance_metrics_collection_start",
            "metric_type": metric_type,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.debug(f"开始收集{metric_type}性能指标", extra=extra)

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
        logger.debug(f"{metric_type}性能指标收集成功", extra=extra)

    @staticmethod
    def log_performance_metrics_collection_failed(
        metric_type: str, error_message: str, collection_time: float, **kwargs: Any
    ) -> None:
        """记录性能指标收集失败"""
        extra: dict[str, Any] = {
            "action": "performance_metrics_collection_failed",
            "success": False,
            "metric_type": metric_type,
            "error_message": error_message,
            "collection_time": collection_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.error(f"{metric_type}性能指标收集失败", extra=extra)

    @staticmethod
    def log_performance_metric_recorded(metric_name: str, value: int | float, **kwargs: Any) -> None:
        """记录性能指标记录"""
        extra: dict[str, Any] = {
            "action": "performance_metric_recorded",
            "metric_name": metric_name,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info(f"性能指标记录: {metric_name} = {value}", extra=extra)

    @staticmethod
    def log_admin_operation_start(operation: str, user_id: int | None = None, **kwargs: Any) -> None:
        """记录Admin操作开始"""
        extra: dict[str, Any] = {
            "action": "admin_operation_start",
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        logger.info(f"开始Admin操作: {operation}", extra=extra)

    @staticmethod
    def log_admin_operation_success(
        operation: str, affected_count: int, processing_time: float, user_id: int | None = None, **kwargs: Any
    ) -> None:
        """记录Admin操作成功"""
        extra: dict[str, Any] = {
            "action": "admin_operation_success",
            "success": True,
            "operation": operation,
            "affected_count": affected_count,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        logger.info(f"Admin操作成功: {operation}", extra=extra)

    @staticmethod
    def log_admin_operation_failed(
        operation: str, error_message: str, processing_time: float, user_id: int | None = None, **kwargs: Any
    ) -> None:
        """记录Admin操作失败"""
        extra: dict[str, Any] = {
            "action": "admin_operation_failed",
            "success": False,
            "operation": operation,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if user_id is not None:
            extra["user_id"] = user_id
        extra.update(kwargs)
        logger.error(f"Admin操作失败: {operation}", extra=extra)

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

    @staticmethod
    def log_cross_module_call(
        source_module: str, target_module: str, service_name: str, method_name: str, **kwargs: Any
    ) -> None:
        """记录跨模块调用"""
        extra: dict[str, Any] = {
            "action": "cross_module_call",
            "source_module": source_module,
            "target_module": target_module,
            "service_name": service_name,
            "method_name": method_name,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.debug(f"跨模块调用: {source_module} -> {target_module}.{service_name}.{method_name}", extra=extra)

    @staticmethod
    def log_document_api_request_start(
        api_name: str,
        page_num: int | None = None,
        page_size: int | None = None,
        sdbh: str | None = None,
        **kwargs: Any,
    ) -> None:
        """记录文书 API 请求开始 (Requirements: 7.1)"""
        extra: dict[str, Any] = {
            "action": "document_api_request_start",
            "api_name": api_name,
            "timestamp": datetime.now().isoformat(),
        }
        if page_num is not None:
            extra["page_num"] = page_num
        if page_size is not None:
            extra["page_size"] = page_size
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)
        logger.info(f"开始调用文书API: {api_name}", extra=extra)

    @staticmethod
    def log_document_api_request_success(
        api_name: str,
        response_code: int,
        processing_time: float,
        document_count: int | None = None,
        total_count: int | None = None,
        page_num: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录文书 API 请求成功 (Requirements: 7.1, 7.2)"""
        extra: dict[str, Any] = {
            "action": "document_api_request_success",
            "success": True,
            "api_name": api_name,
            "response_code": response_code,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if document_count is not None:
            extra["document_count"] = document_count
        if total_count is not None:
            extra["total_count"] = total_count
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)
        logger.info(f"文书API调用成功: {api_name}", extra=extra)

    @staticmethod
    def log_document_api_request_failed(
        api_name: str,
        error_message: str,
        processing_time: float,
        response_code: int | None = None,
        page_num: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录文书 API 请求失败 (Requirements: 7.1, 7.4)"""
        extra: dict[str, Any] = {
            "action": "document_api_request_failed",
            "success": False,
            "api_name": api_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if response_code is not None:
            extra["response_code"] = response_code
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)
        logger.error(f"文书API调用失败: {api_name}", extra=extra)

    @staticmethod
    def log_document_query_statistics(
        total_found: int,
        processed_count: int,
        skipped_count: int,
        failed_count: int,
        query_method: str = "api",
        credential_id: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录文书查询统计信息 (Requirements: 7.2)"""
        extra: dict[str, Any] = {
            "action": "document_query_statistics",
            "total_found": total_found,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "query_method": query_method,
            "timestamp": datetime.now().isoformat(),
        }
        if credential_id is not None:
            extra["credential_id"] = credential_id
        extra.update(kwargs)
        logger.info(
            f"文书查询统计: 发现={total_found}, 处理={processed_count}, 跳过={skipped_count}, 失败={failed_count}",
            extra=extra,
        )

    @staticmethod
    def log_document_download_start(
        document_name: str, url: str | None = None, sdbh: str | None = None, **kwargs: Any
    ) -> None:
        """记录文书下载开始 (Requirements: 7.1)"""
        extra: dict[str, Any] = {
            "action": "document_download_start",
            "document_name": document_name,
            "timestamp": datetime.now().isoformat(),
        }
        if url is not None:
            extra["url_prefix"] = url[:50] + "..." if len(url) > 50 else url
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)
        logger.info(f"开始下载文书: {document_name}", extra=extra)

    @staticmethod
    def log_document_download_success(
        document_name: str, file_size: int, processing_time: float, save_path: str | None = None, **kwargs: Any
    ) -> None:
        """记录文书下载成功 (Requirements: 7.1, 7.2)"""
        extra: dict[str, Any] = {
            "action": "document_download_success",
            "success": True,
            "document_name": document_name,
            "file_size": file_size,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if save_path is not None:
            extra["save_path"] = save_path
        extra.update(kwargs)
        logger.info(f"文书下载成功: {document_name}", extra=extra)

    @staticmethod
    def log_document_download_failed(
        document_name: str, error_message: str, processing_time: float, **kwargs: Any
    ) -> None:
        """记录文书下载失败 (Requirements: 7.1, 7.4)"""
        extra: dict[str, Any] = {
            "action": "document_download_failed",
            "success": False,
            "document_name": document_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.error(f"文书下载失败: {document_name}", extra=extra)

    @staticmethod
    def log_fallback_triggered(
        from_method: str,
        to_method: str,
        reason: str,
        error_type: str | None = None,
        credential_id: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录降级触发 (Requirements: 7.3)"""
        extra: dict[str, Any] = {
            "action": "fallback_triggered",
            "from_method": from_method,
            "to_method": to_method,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        if error_type is not None:
            extra["error_type"] = error_type
        if credential_id is not None:
            extra["credential_id"] = credential_id
        extra.update(kwargs)
        logger.warning(f"降级触发: {from_method} -> {to_method}, 原因: {reason}", extra=extra)

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
        """记录 API 详细错误信息 (Requirements: 7.4)"""
        extra: dict[str, Any] = {
            "action": "api_error_detail",
            "api_name": api_name,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
        }
        if stack_trace is not None:
            extra["stack_trace"] = stack_trace
        if request_params is not None:
            extra["request_params"] = {k: v for k, v in request_params.items() if k not in ["token", "password"]}
        if response_data is not None:
            extra["response_data"] = response_data
        extra.update(kwargs)
        logger.error(f"API错误详情: {api_name} - {error_type}: {error_message}", extra=extra)
