"""文档、AI、音频相关日志 Mixin"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DocumentLoggingMixin:
    """文档、AI、音频相关日志方法"""

    @staticmethod
    def log_document_creation_start(scraper_task_id: int, case_id: int | None = None, **kwargs: Any) -> None:
        """记录文档创建开始"""
        extra: dict[str, Any] = {
            "action": "document_creation_start",
            "scraper_task_id": scraper_task_id,
            "timestamp": datetime.now().isoformat(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)
        logger.info("开始创建文档记录", extra=extra)

    @staticmethod
    def log_document_creation_success(
        document_id: int, scraper_task_id: int, case_id: int | None = None, **kwargs: Any
    ) -> None:
        """记录文档创建成功"""
        extra: dict[str, Any] = {
            "action": "document_creation_success",
            "success": True,
            "document_id": document_id,
            "scraper_task_id": scraper_task_id,
            "timestamp": datetime.now().isoformat(),
        }
        if case_id is not None:
            extra["case_id"] = case_id
        extra.update(kwargs)
        logger.info("文档记录创建成功", extra=extra)

    @staticmethod
    def log_document_status_update(document_id: int, old_status: str, new_status: str, **kwargs: Any) -> None:
        """记录文档状态更新"""
        extra: dict[str, Any] = {
            "action": "document_status_update",
            "document_id": document_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("文档状态更新", extra=extra)

    @staticmethod
    def log_document_processing_start(file_type: str, file_size: int | None = None, **kwargs: Any) -> None:
        """记录文档处理开始"""
        extra: dict[str, Any] = {
            "action": "document_processing_start",
            "file_type": file_type,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.info(f"开始处理{file_type}文档", extra=extra)

    @staticmethod
    def log_document_processing_success(
        file_type: str, processing_time: float, content_length: int, file_size: int | None = None, **kwargs: Any
    ) -> None:
        """记录文档处理成功"""
        extra: dict[str, Any] = {
            "action": "document_processing_success",
            "success": True,
            "file_type": file_type,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.info(f"{file_type}文档处理成功", extra=extra)

    @staticmethod
    def log_document_processing_failed(
        file_type: str, error_message: str, processing_time: float, file_size: int | None = None, **kwargs: Any
    ) -> None:
        """记录文档处理失败"""
        extra: dict[str, Any] = {
            "action": "document_processing_failed",
            "success": False,
            "file_type": file_type,
            "error_message": error_message,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.error(f"{file_type}文档处理失败", extra=extra)

    @staticmethod
    def log_ai_filename_generation_start(content_length: int, **kwargs: Any) -> None:
        """记录AI文件名生成开始"""
        extra: dict[str, Any] = {
            "action": "ai_filename_generation_start",
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("开始AI文件名生成", extra=extra)

    @staticmethod
    def log_ai_filename_generation_success(
        generated_filename: str, processing_time: float, content_length: int, **kwargs: Any
    ) -> None:
        """记录AI文件名生成成功"""
        extra: dict[str, Any] = {
            "action": "ai_filename_generation_success",
            "success": True,
            "generated_filename": generated_filename,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.info("AI文件名生成成功", extra=extra)

    @staticmethod
    def log_ai_filename_generation_failed(
        error_message: str, processing_time: float, content_length: int, **kwargs: Any
    ) -> None:
        """记录AI文件名生成失败"""
        extra: dict[str, Any] = {
            "action": "ai_filename_generation_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "content_length": content_length,
            "timestamp": datetime.now().isoformat(),
        }
        extra.update(kwargs)
        logger.error("AI文件名生成失败", extra=extra)

    @staticmethod
    def log_audio_transcription_start(file_format: str, file_size: int | None = None, **kwargs: Any) -> None:
        """记录音频转录开始"""
        extra: dict[str, Any] = {
            "action": "audio_transcription_start",
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.info("开始音频转录", extra=extra)

    @staticmethod
    def log_audio_transcription_success(
        transcription_length: int,
        processing_time: float,
        file_format: str,
        file_size: int | None = None,
        **kwargs: Any,
    ) -> None:
        """记录音频转录成功"""
        extra: dict[str, Any] = {
            "action": "audio_transcription_success",
            "success": True,
            "transcription_length": transcription_length,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.info("音频转录成功", extra=extra)

    @staticmethod
    def log_audio_transcription_failed(
        error_message: str, processing_time: float, file_format: str, file_size: int | None = None, **kwargs: Any
    ) -> None:
        """记录音频转录失败"""
        extra: dict[str, Any] = {
            "action": "audio_transcription_failed",
            "success": False,
            "error_message": error_message,
            "processing_time": processing_time,
            "file_format": file_format,
            "timestamp": datetime.now().isoformat(),
        }
        if file_size is not None:
            extra["file_size"] = file_size
        extra.update(kwargs)
        logger.error("音频转录失败", extra=extra)
