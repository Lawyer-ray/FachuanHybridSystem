"""Business workflow orchestration."""

import logging
from datetime import datetime
from typing import Any

from django.db import transaction

from apps.automation.services.court_document_recognition.data_classes import BindingResult, DocumentType
from apps.automation.services.court_document_recognition.repositories.case_lookup_repo import CaseLookupRepo
from apps.automation.services.court_document_recognition.repositories.document_recognition_task_repo import (
    DocumentRecognitionTaskRepo,
)
from apps.automation.services.court_document_recognition.side_effects.case_log_side_effects import CaseLogSideEffects
from apps.automation.services.court_document_recognition.side_effects.document_file_side_effects import (
    DocumentFileSideEffects,
)
from apps.automation.services.court_document_recognition.side_effects.notification_side_effects import (
    NotificationSideEffects,
)
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.automation")


class CaseBindingWorkflow:
    def __init__(
        self,
        *,
        case_service: Any,
        case_lookup_repo: CaseLookupRepo | None = None,
        task_repo: DocumentRecognitionTaskRepo | None = None,
        case_log_side_effects: CaseLogSideEffects | None = None,
        document_file_side_effects: DocumentFileSideEffects | None = None,
        notification_side_effects: NotificationSideEffects | None = None,
    ) -> None:
        self.case_service = case_service
        self.case_lookup_repo = case_lookup_repo or CaseLookupRepo(case_service)
        self.task_repo = task_repo or DocumentRecognitionTaskRepo()
        self.case_log_side_effects = case_log_side_effects or CaseLogSideEffects(case_service)
        self.document_file_side_effects = document_file_side_effects or DocumentFileSideEffects()
        self.notification_side_effects = notification_side_effects or NotificationSideEffects()

    def format_log_content(
        self, document_type: DocumentType, case_number: str | None, key_time: datetime | None, raw_text: str
    ) -> str:
        type_labels = {
            DocumentType.SUMMONS: "传票",
            DocumentType.EXECUTION_RULING: "执行裁定书",
            DocumentType.OTHER: "其他文书",
        }

        type_label = type_labels.get(document_type, "法院文书")
        lines: list[Any] = []

        if case_number:
            lines.append(f"案号:{case_number}")

        if key_time:
            if document_type == DocumentType.SUMMONS:
                lines.append(f"开庭时间:{key_time.strftime('%Y-%m-%d %H:%M')}")
            elif document_type == DocumentType.EXECUTION_RULING:
                lines.append(f"保全到期时间:{key_time.strftime('%Y-%m-%d')}")

        if raw_text:
            text_preview = raw_text[:500]
            if len(raw_text) > 500:
                text_preview += "..."
            lines.append(f"\n文书内容摘要:\n{text_preview}")

        return "\n".join(lines)

    def bind_document_to_case(
        self,
        *,
        case_number: str,
        document_type: DocumentType,
        content: str,
        key_time: datetime | None,
        file_path: str,
        user: Any | None = None,
    ) -> BindingResult:
        if not case_number:
            return BindingResult.failure_result(message="未识别到案号,无法绑定案件", error_code="CASE_NUMBER_NOT_FOUND")

        case_id = self.case_lookup_repo.find_case_id_by_number(case_number)
        if case_id is None:
            return BindingResult.failure_result(
                message=f"未找到案号 {case_number} 对应的案件", error_code="CASE_NOT_FOUND"
            )

        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(message=f"案件 {case_id} 不存在", error_code="CASE_NOT_FOUND")

        case_name = case_dto.name

        try:
            case_log_id = self.case_log_side_effects.create_case_log(
                case_id=case_id,
                content=content,
                reminder_time=key_time,
                file_path=file_path,
                document_type=document_type,
                user=user,
            )
            logger.info(
                "文书绑定成功",
                extra={
                    "action": "bind_document_to_case",
                    "case_number": case_number,
                    "case_id": case_id,
                    "case_name": case_name,
                    "case_log_id": case_log_id,
                    "document_type": document_type.value,
                },
            )
            return BindingResult.success_result(case_id=case_id, case_name=case_name, case_log_id=case_log_id)
        except NotFoundError as e:
            return BindingResult.failure_result(message=str(e), error_code="CASE_NOT_FOUND")
        except Exception as e:
            logger.exception(
                "文书绑定失败",
                extra={
                    "action": "bind_document_to_case",
                    "case_number": case_number,
                    "case_id": case_id,
                    "document_type": document_type.value,
                    "error": str(e),
                },
            )
            return BindingResult.failure_result(message=f"绑定失败:{e!s}", error_code="BINDING_ERROR")

    @transaction.atomic
    def manual_bind_document_to_case(self, *, task_id: int, case_id: int, user: Any | None = None) -> BindingResult:
        task = self.task_repo.get(task_id)
        if not task:
            return BindingResult.failure_result(message=f"任务 {task_id} 不存在", error_code="TASK_NOT_FOUND")

        if task.binding_success:
            return BindingResult.failure_result(message="任务已绑定到案件", error_code="ALREADY_BOUND")

        case_dto = self.case_service.get_case_by_id_internal(case_id)
        if case_dto is None:
            return BindingResult.failure_result(message=f"案件 {case_id} 不存在", error_code="CASE_NOT_FOUND")

        case_name = case_dto.name

        document_type = DocumentType.OTHER
        if task.document_type:
            try:
                document_type = DocumentType(task.document_type)
            except ValueError:
                document_type = DocumentType.OTHER

        file_path = task.file_path
        renamed_file_path = self.document_file_side_effects.rename_for_manual_bind(
            file_path=file_path, document_type=document_type, case_name=case_name
        )
        if renamed_file_path != file_path:
            task.renamed_file_path = renamed_file_path
            task.save(update_fields=["renamed_file_path"])

        content = self.format_log_content(
            document_type=document_type,
            case_number=task.case_number,
            key_time=task.key_time,
            raw_text=task.raw_text or "",
        )

        try:
            case_log_id = self.case_log_side_effects.create_case_log(
                case_id=case_id,
                content=content,
                reminder_time=task.key_time,
                file_path=renamed_file_path,
                document_type=document_type,
                user=user,
            )
        except Exception as e:
            logger.exception(
                "创建案件日志失败(手动绑定)",
                extra={
                    "action": "manual_bind_document_to_case",
                    "task_id": task_id,
                    "case_id": case_id,
                    "document_type": document_type.value,
                    "error": str(e),
                },
            )
            return BindingResult.failure_result(message=f"创建案件日志失败:{e!s}", error_code="LOG_CREATE_ERROR")

        case_obj = self.case_service.get_case_model_internal(case_id)
        case_log_obj = self.case_service.get_case_log_model_internal(case_log_id)

        if case_obj is None:
            raise NotFoundError(f"案件 {case_id} 不存在")
        if case_log_obj is None:
            raise NotFoundError(f"案件日志 {case_log_id} 不存在")

        task.case = case_obj
        task.case_log = case_log_obj
        task.binding_success = True
        task.binding_message = f"手动绑定到案件 {case_name}"
        task.binding_error_code = None
        task.save(update_fields=["case", "case_log", "binding_success", "binding_message", "binding_error_code"])

        self.notification_side_effects.trigger(task, case_id, case_name, document_type)

        return BindingResult.success_result(case_id=case_id, case_name=case_name, case_log_id=case_log_id)
