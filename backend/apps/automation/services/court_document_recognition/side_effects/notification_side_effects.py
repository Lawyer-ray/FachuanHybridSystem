"""Side effect handlers."""

import logging
from typing import Any, cast

from apps.automation.services.court_document_recognition.data_classes import DocumentType

logger = logging.getLogger("apps.automation")


class NotificationSideEffects:
    def trigger(self, task: Any, case_id: int, case_name: str, document_type: DocumentType) -> None:
        try:
            from apps.automation.services.court_document_recognition.notification_service import (
                DocumentRecognitionNotificationService,
            )

            notification_service = DocumentRecognitionNotificationService()
            file_path = task.renamed_file_path or task.file_path

            result = notification_service.send_notification(
                case_id=case_id,
                document_type=document_type.value,
                case_number=task.case_number,
                key_time=task.key_time,
                file_path=file_path,
                case_name=case_name,
            )

            task.notification_sent = result.success
            task.notification_sent_at = result.sent_at
            task.notification_file_sent = result.file_sent
            if not result.success:
                task.notification_error = result.message
                logger.warning(
                    "文书识别通知发送失败",
                    extra={
                        "action": "trigger_notification",
                        "task_id": cast(int, task.id),
                        "case_id": case_id,
                        "error": result.message,
                    },
                )
            else:
                logger.info(
                    "文书识别通知发送成功",
                    extra={
                        "action": "trigger_notification",
                        "task_id": cast(int, task.id),
                        "case_id": case_id,
                        "file_sent": result.file_sent,
                    },
                )

            task.save(
                update_fields=[
                    "notification_sent",
                    "notification_sent_at",
                    "notification_file_sent",
                    "notification_error",
                ]
            )

        except Exception as e:
            logger.warning(
                f"发送飞书通知失败:{e}",
                extra={
                    "action": "trigger_notification",
                    "task_id": getattr(task, "id", None),
                    "case_id": case_id,
                    "error": str(e),
                },
            )
            try:
                task.notification_sent = False
                task.notification_error = str(e)
                task.save(update_fields=["notification_sent", "notification_error"])
            except Exception:
                logger.exception("操作失败")

                return
