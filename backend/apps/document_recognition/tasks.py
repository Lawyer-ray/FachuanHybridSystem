"""Async tasks for document recognition."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("apps.document_recognition")


def execute_document_recognition_task(task_id: int) -> dict[str, Any] | None:  # pragma: no cover
    """Execute one document recognition task in Django-Q worker."""
    from django.utils import timezone

    from apps.core.interfaces import ServiceLocator
    from apps.document_recognition.models import DocumentRecognitionStatus, DocumentRecognitionTask

    logger.info("开始执行文书识别任务 #%s", task_id)

    try:
        task = DocumentRecognitionTask.objects.get(id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        logger.error("识别任务不存在: %s", task_id)
        return None

    task.status = DocumentRecognitionStatus.PROCESSING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])

    try:
        service = ServiceLocator.get_court_document_recognition_service()
        # 管线预绑定（法院短信入口）：案件与日志已由来源管线建好，识别只做提取+候选
        prebound_case_log_id = task.case_log_id if task.source_court_sms_id else None
        prebound_case_id = task.case_id if task.source_court_sms_id else None
        result = service.recognize_document(
            task.file_path,
            user=None,
            prebound_case_id=prebound_case_id,
            prebound_case_log_id=prebound_case_log_id,
            llm_model=task.llm_model,
        )

        recognition = result.recognition
        task.document_type = recognition.document_type.value
        task.case_number = recognition.case_number
        task.key_time = recognition.key_time
        task.confidence = recognition.confidence
        task.extraction_method = recognition.extraction_method
        task.llm_model = recognition.llm_model
        task.llm_backend = recognition.llm_backend
        task.llm_latency_ms = recognition.llm_latency_ms
        task.degraded = recognition.degraded
        task.raw_text = recognition.raw_text[:10000] if recognition.raw_text else None
        task.party_names = result.party_names
        task.renamed_file_path = result.file_path

        if result.binding:
            task.binding_success = result.binding.success
            task.binding_message = result.binding.message
            task.binding_error_code = result.binding.error_code
            if result.binding.case_id:
                task.case_id = result.binding.case_id
            if result.binding.case_log_id:
                task.case_log_id = result.binding.case_log_id

        task.status = DocumentRecognitionStatus.SUCCESS
        task.finished_at = timezone.now()
        task.save()

        # 日期候选落库（幂等：已有候选行时跳过）
        from apps.document_recognition.services import date_candidate_service

        drafts = [
            date_candidate_service.DateCandidateDraft(
                due_at=datetime.fromisoformat(item["due_at"]),
                reminder_type=item["reminder_type"],
                context_text=item["context_text"],
                source=item["source"],
                confidence=item["confidence"],
            )
            for item in result.date_candidates
        ]
        date_candidate_service.persist_candidates(task, drafts)

        # 管线模式（来自法院短信）不重复发通知——通知由来源管线自己发
        if result.binding and result.binding.success and not task.source_court_sms_id:
            _send_recognition_notification(task, result)

        logger.info("文书识别任务 #%s 完成: %s", task_id, task.document_type)
        return {"task_id": task_id, "status": "success", "document_type": task.document_type}

    except Exception as exc:
        logger.error("文书识别任务 #%s 失败: %s", task_id, exc, exc_info=True)

        task.status = DocumentRecognitionStatus.FAILED
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at"])

        return {"task_id": task_id, "status": "failed", "error": str(exc)}


def _send_recognition_notification(task: Any, result: Any) -> None:
    """Send recognition notification after successful binding."""
    try:
        from apps.document_recognition.services.notification_service import DocumentRecognitionNotificationService

        notification_service = DocumentRecognitionNotificationService()
        file_path = task.renamed_file_path or task.file_path

        notification_result = notification_service.send_notification(
            case_id=result.binding.case_id,
            document_type=task.document_type,
            case_number=task.case_number,
            key_time=task.key_time,
            file_path=file_path,
            case_name=result.binding.case_name,
            date_count=task.date_candidates.count(),
        )

        task.notification_sent = notification_result.success
        task.notification_sent_at = notification_result.sent_at
        task.notification_file_sent = notification_result.file_sent

        if not notification_result.success:
            task.notification_error = notification_result.message
            logger.warning(
                "文书识别通知发送失败: task_id=%s, error=%s",
                task.id,
                notification_result.message,
            )
        else:
            logger.info(
                "文书识别通知发送成功: task_id=%s, file_sent=%s",
                task.id,
                notification_result.file_sent,
            )

        task.save(
            update_fields=[
                "notification_sent",
                "notification_sent_at",
                "notification_file_sent",
                "notification_error",
            ]
        )

    except Exception as exc:
        logger.error("发送文书识别通知异常: task_id=%s, error=%s", task.id, exc, exc_info=True)
        task.notification_sent = False
        task.notification_error = str(exc)
        task.save(update_fields=["notification_sent", "notification_error"])
