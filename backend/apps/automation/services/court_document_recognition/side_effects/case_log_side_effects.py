"""Side effect handlers."""

import logging
import os
from datetime import datetime
from typing import Any

from apps.automation.services.court_document_recognition.data_classes import DocumentType
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.automation")


class CaseLogSideEffects:
    def __init__(self, case_service: Any) -> None:
        self.case_service = case_service

    def get_relative_media_path(self, file_path: str) -> str:
        from apps.core.config import get_config

        media_root = str(get_config("django.media_root", "") or "")
        if not os.path.isabs(file_path):
            return file_path
        if media_root and file_path.startswith(media_root):
            return os.path.relpath(file_path, media_root)
        logger.warning("文件路径不在 MEDIA_ROOT 下", extra={})
        return file_path

    def create_case_log(
        self,
        *,
        case_id: int,
        content: str,
        reminder_time: datetime | None,
        file_path: str,
        document_type: DocumentType | None = None,
        user: Any | None = None,
    ) -> int:
        user_id = getattr(user, "id", None) if user else None

        case_log_id = self.case_service.create_case_log_internal(case_id=case_id, content=content, user_id=user_id)

        if reminder_time:
            self.update_log_reminder(case_log_id, reminder_time, document_type)

        if file_path:
            file_name = os.path.basename(file_path)
            relative_path = self.get_relative_media_path(file_path)
            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=case_log_id, file_path=relative_path, file_name=file_name
            )
            if not success:
                logger.warning("添加日志附件失败", extra={})

        return case_log_id  # type: ignore[no-any-return]

    def update_log_reminder(
        self, case_log_id: int, reminder_time: datetime, document_type: DocumentType | None = None
    ) -> None:
        reminder_type = "other"
        if document_type == DocumentType.SUMMONS:
            reminder_type = "hearing"
        elif document_type == DocumentType.EXECUTION_RULING:
            reminder_type = "asset_preservation_expires"

        try:
            success = self.case_service.update_case_log_reminder_internal(
                case_log_id=case_log_id, reminder_time=reminder_time, reminder_type=reminder_type
            )
            if success:
                logger.debug(
                    "更新日志提醒成功",
                    extra={
                        "action": "update_log_reminder",
                        "case_log_id": case_log_id,
                        "reminder_time": str(reminder_time),
                        "reminder_type": reminder_type,
                    },
                )
            else:
                logger.warning("更新日志提醒失败", extra={"action": "update_log_reminder", "case_log_id": case_log_id})
        except Exception as e:
            raise ValidationException(message="更新日志提醒失败", code="REMINDER_UPDATE_FAILED", errors={}) from e
