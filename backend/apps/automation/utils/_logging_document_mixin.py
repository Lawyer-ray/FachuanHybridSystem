"""文档记录相关日志 Mixin"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DocumentLoggingMixin:
    """文档记录相关日志方法"""

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
