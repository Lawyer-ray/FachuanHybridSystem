"""Utility functions."""

from __future__ import annotations

from typing import Any

from apps.core.telemetry.time import utc_now_iso

from .common import get_logger


class AutomationAiLoggerMixin:
    @staticmethod
    def log_ai_filename_generation_start(content_length: int, **kwargs: Any) -> None:
        extra = {
            "action": "ai_filename_generation_start",
            "content_length": content_length,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().info("开始AI文件名生成", extra=extra)

    @staticmethod
    def log_ai_filename_generation_success(
        generated_filename: str, processing_time: float, content_length: int, **kwargs: Any
    ) -> None:
        extra = {
            "action": "ai_filename_generation_success",
            "success": True,
            "generated_filename": generated_filename,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().info("AI文件名生成成功", extra=extra)

    @staticmethod
    def log_ai_filename_generation_failed(
        error_message: str, processing_time: float, content_length: int, **kwargs: Any
    ) -> None:
        extra = {
            "action": "ai_filename_generation_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().error("AI文件名生成失败", extra=extra)

    @staticmethod
    def log_audio_transcription_start(file_format: str, file_size: int | None = None, **kwargs: Any) -> None:
        extra = {
            "action": "audio_transcription_start",
            "file_format": file_format,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size  # type: ignore[assignment]
        extra.update(kwargs)

        get_logger().info("开始音频转录", extra=extra)

    @staticmethod
    def log_audio_transcription_success(
        transcription_length: int, processing_time: float, file_format: str, file_size: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "audio_transcription_success",
            "success": True,
            "transcription_length": transcription_length,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)

        get_logger().info("音频转录成功", extra=extra)

    @staticmethod
    def log_audio_transcription_failed(
        error_message: str, processing_time: float, file_format: str, file_size: int | None = None, **kwargs: Any
    ) -> None:
        extra = {
            "action": "audio_transcription_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": utc_now_iso(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)

        get_logger().error("音频转录失败", extra=extra)

    @staticmethod
    def log_performance_metrics_collection_start(metric_type: str, **kwargs: Any) -> None:
        extra = {
            "action": "performance_metrics_collection_start",
            "metric_type": metric_type,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().debug(f"开始收集{metric_type}性能指标", extra=extra)

    @staticmethod
    def log_performance_metrics_collection_success(
        metric_type: str, metrics_count: int, collection_time: float, **kwargs: Any
    ) -> None:
        extra = {
            "action": "performance_metrics_collection_success",
            "success": True,
            "metric_type": metric_type,
            "metrics_count": metrics_count,
            "collection_time": collection_time,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().debug(f"{metric_type}性能指标收集成功", extra=extra)

    @staticmethod
    def log_performance_metrics_collection_failed(
        metric_type: str, error_message: str, collection_time: float, **kwargs: Any
    ) -> None:
        extra = {
            "action": "performance_metrics_collection_failed",
            "success": False,
            "metric_type": metric_type,
            "error_message": error_message,
            "collection_time": collection_time,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().error(f"{metric_type}性能指标收集失败", extra=extra)

    @staticmethod
    def log_performance_metric_recorded(metric_name: str, value: int | float, **kwargs: Any) -> None:
        extra = {
            "action": "performance_metric_recorded",
            "metric_name": metric_name,
            "value": value,
            "timestamp": utc_now_iso(),
        }
        extra.update(kwargs)

        get_logger().info(f"性能指标记录: {metric_name} = {value}", extra=extra)
