"""Utility functions."""

from __future__ import annotations

from typing import Any

from apps.core.telemetry.time import utc_now_iso

from .common import get_logger, sanitize_url


class AutomationDocumentLoggerMixin:
    @staticmethod
    def log_document_creation_start(scraper_task_id: int, case_id: int | None = None, **kwargs: Any) -> None:
        extra = {
            "action": "document_creation_start",
            "scraper_task_id": scraper_task_id,
            "timestamp": utc_now_iso(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)

        get_logger().info("开始创建文档记录", extra=extra)

    @staticmethod
    def log_document_creation_success(
        document_id: int, scraper_task_id: int, case_id: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_creation_success",
            "success": True,
            "document_id": document_id,
            "scraper_task_id": scraper_task_id,
            "timestamp": utc_now_iso(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)

        get_logger().info("文档记录创建成功", extra=extra)

    @staticmethod
    def log_document_status_update(document_id: int, old_status: str, new_status: str, **kwargs: Any) -> None:
        extra = {
            "action": "document_status_update",
            "document_id": document_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().info("文档状态更新", extra=extra)

    @staticmethod
    def log_document_processing_start(file_type: str, file_size: int | None = None, **kwargs: Any) -> None:
        extra = {
            "action": "document_processing_start",
            "file_type": file_type,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size  # type: ignore[assignment]
        extra.update(kwargs)

        get_logger().info(f"开始处理{file_type}文档", extra=extra)

    @staticmethod
    def log_document_processing_success(
        file_type: str, processing_time: float, content_length: int, file_size: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_processing_success",
            "success": True,
            "file_type": file_type,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)

        get_logger().info(f"{file_type}文档处理成功", extra=extra)

    @staticmethod
    def log_document_processing_failed(
        file_type: str, error_message: str, processing_time: float, file_size: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_processing_failed",
            "success": False,
            "file_type": file_type,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)

        get_logger().error(f"{file_type}文档处理失败", extra=extra)

    @staticmethod
    def log_document_api_request_start(
        api_name: str,
        page_num: int | None = None,
        page_size: int | None = None,
        sdbh: str | None = None,
        **kwargs: Any,
    ) -> None:
        extra = {
            "action": "document_api_request_start",
            "api_name": api_name,
            "timestamp": utc_now_iso(),
        }
        if page_num is not None:
            extra["page_num"] = page_num  # type: ignore[assignment]
        if page_size is not None:
            extra["page_size"] = page_size  # type: ignore[assignment]
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)

        get_logger().info(f"开始调用文书API: {api_name}", extra=extra)

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
        extra = {
            "action": "document_api_request_success",
            "success": True,
            "api_name": api_name,
            "response_code": response_code,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if document_count is not None:
            extra["document_count"] = document_count
        if total_count is not None:
            extra["total_count"] = total_count
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)

        get_logger().info(f"文书API调用成功: {api_name}", extra=extra)

    @staticmethod
    def log_document_api_request_failed(
        api_name: str,
        error_message: str,
        processing_time: float,
        response_code: int | None = None,
        page_num: int | None = None,
        **kwargs: Any,
    ) -> None:
        extra = {
            "action": "document_api_request_failed",
            "success": False,
            "api_name": api_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if response_code is not None:
            extra["response_code"] = response_code
        if page_num is not None:
            extra["page_num"] = page_num
        extra.update(kwargs)

        get_logger().error(f"文书API调用失败: {api_name}", extra=extra)

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
        extra = {
            "action": "document_query_statistics",
            "total_found": total_found,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "query_method": query_method,
            "timestamp": utc_now_iso(),
        }
        if credential_id is not None:
            extra["credential_id"] = credential_id
        extra.update(kwargs)

        get_logger().info(
            f"文书查询统计: 发现={total_found}, 处理={processed_count}, 跳过={skipped_count}, 失败={failed_count}",
            extra=extra,
        )

    @staticmethod
    def log_document_download_start(
        document_name: str, url: str | None = None, sdbh: str | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_download_start",
            "document_name": document_name,
            "timestamp": utc_now_iso(),
        }
        if url is not None:
            safe_url = sanitize_url(url)
            extra["url_prefix"] = safe_url[:50] + "..." if len(safe_url) > 50 else safe_url
        if sdbh is not None:
            extra["sdbh"] = sdbh
        extra.update(kwargs)

        get_logger().info(f"开始下载文书: {document_name}", extra=extra)

    @staticmethod
    def log_document_download_success(
        document_name: str, file_size: int, processing_time: float, save_path: str | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_download_success",
            "success": True,
            "document_name": document_name,
            "file_size": file_size,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        if save_path is not None:
            extra["save_path"] = save_path
        extra.update(kwargs)

        get_logger().info(f"文书下载成功: {document_name}", extra=extra)

    @staticmethod
    def log_document_download_failed(
        document_name: str, error_message: str, processing_time: float, **kwargs: Any
    ) -> None:
        extra = {
            "action": "document_download_failed",
            "success": False,
            "document_name": document_name,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().error(f"文书下载失败: {document_name}", extra=extra)
