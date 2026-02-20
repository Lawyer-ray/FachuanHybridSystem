"""Business logic services."""

from django.utils.translation import gettext_lazy as _
import logging
import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.dtos import GenerationTaskDTO
from apps.core.exceptions import NotFoundError, ValidationException
from apps.litigation_ai.models import LitigationSession

logger = logging.getLogger("apps.litigation_ai")


class DocumentGeneratorService:
    @transaction.atomic
    def generate_document(self, session_id: str, template_id: int | None = None) -> GenerationTaskDTO:
        from apps.litigation_ai.services.wiring import get_conversation_history_service, get_generation_task_service

        session = LitigationSession.objects.filter(session_id=session_id).select_related("case").first()
        if not session:
            raise NotFoundError(
                message=_("会话不存在"),
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        history_service = get_conversation_history_service()
        last_messages = history_service.list_messages_internal(
            litigation_session_id=session.id,
            role="assistant",
            limit=1,
            order="desc",
        )
        last_message = last_messages[0] if last_messages else None
        if not last_message:
            raise ValidationException(
                message=_("未找到生成的内容"),
                code="NO_GENERATED_CONTENT",
                errors={"session_id": "会话中没有生成的内容"},
            )

        task_service = get_generation_task_service()
        task = task_service.create_ai_task_internal(
            case_id=session.case_id,
            litigation_session_id=session.id,
            document_type=session.document_type or "",
            template_id=template_id,
            created_by_id=session.user_id,
            metadata={"session_id": session_id, "content_length": len(last_message.content)},
        )

        try:
            structured = self._get_structured_content(session, last_message.content)
            case_dto = self._get_case_dto(session.case_id)
            filename, doc_bytes = self._render(case_dto, session.document_type, structured)
            relative_path = self._save_document(filename, doc_bytes, session.case_id)

            metadata_updates = {
                "generation_duration_ms": int((timezone.now() - task.created_at).total_seconds() * 1000),
                "total_tokens": (session.metadata or {}).get("total_tokens", 0),
            }
            return task_service.mark_task_completed_internal(
                task_id=task.id,
                result_file=relative_path,
                metadata_updates=metadata_updates,
            )
        except Exception as e:
            task_service.mark_task_failed_internal(task_id=task.id, error_message=str(e))
            raise ValidationException(
                message=_("文档生成失败"),
                code="DOCUMENT_GENERATION_FAILED",
                errors={"error": str(e)},
            ) from e

    def get_task_status(self, task_id: int, user: Any | None = None) -> GenerationTaskDTO:
        from apps.core.exceptions import NotFoundError, PermissionDenied
        from apps.litigation_ai.services.wiring import get_generation_task_service

        task = get_generation_task_service().get_task_internal(task_id)
        if not task:
            raise NotFoundError(
                message=_("任务不存在"),
                code="TASK_NOT_FOUND",
                errors={"task_id": f"ID 为 {task_id} 的任务不存在"},
            )

        if user and task.created_by_id != user.id:
            raise PermissionDenied(message=_("无权限访问此任务"), code="PERMISSION_DENIED")

        return task

    def _get_structured_content(self, session: LitigationSession, raw_content: str) -> dict[str, str]:
        draft = (session.metadata or {}).get("draft")
        if isinstance(draft, dict):
            if session.document_type in ["complaint", "counterclaim"] and (
                draft.get("litigation_request") or draft.get("facts_and_reasons")
            ):
                return {
                    "litigation_request": draft.get("litigation_request", ""),
                    "facts_and_reasons": draft.get("facts_and_reasons", ""),
                }
            if session.document_type in ["defense", "counterclaim_defense"] and draft.get("defense_reason"):
                return {
                    "defense_opinion": draft.get("defense_opinion", ""),
                    "defense_reason": draft.get("defense_reason", ""),
                }

        if session.document_type in ["complaint", "counterclaim"]:
            lr_match = re.search(r"诉讼请求[::]\s*\n(.*?)(?=\n\s*事实与理由|$)", raw_content, flags=re.DOTALL)
            fr_match = re.search(r"事实与理由[::]\s*\n(.*?)$", raw_content, flags=re.DOTALL)
            return {
                "litigation_request": (lr_match.group(1).strip() if lr_match else ""),
                "facts_and_reasons": (fr_match.group(1).strip() if fr_match else ""),
            }

        dr_match = re.search(r"答辩理由[::]\s*\n(.*?)$", raw_content, flags=re.DOTALL)
        return {"defense_reason": (dr_match.group(1).strip() if dr_match else "")}

    def _get_case_dto(self, case_id: int) -> Any:
        from apps.litigation_ai.services.wiring import get_case_service

        case_service = get_case_service()
        case_dto = case_service.get_case_by_id_internal(case_id)
        if not case_dto:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})
        return case_dto

    def _render(self, case_dto: Any, document_type: str, structured: dict[str, str]) -> tuple[str, bytes]:
        from apps.litigation_ai.dependencies import (
            get_complaint_output_class,
            get_defense_output_class,
            get_litigation_generation_service,
        )

        ComplaintOutput = get_complaint_output_class()
        DefenseOutput = get_defense_output_class()
        service = get_litigation_generation_service()
        if document_type in ["complaint", "counterclaim"]:
            complaint_output = ComplaintOutput(
                title=f"{case_dto.cause_of_action or '民事纠纷'}起诉状",
                parties=[],
                litigation_request=structured.get("litigation_request", ""),
                facts_and_reasons=structured.get("facts_and_reasons", ""),
                evidence=[],
            )
            context = service._build_complaint_context(case_dto, complaint_output)
            filename = service._generate_filename(case_dto.id, "complaint")
            doc_bytes = service._render_template(service.COMPLAINT_TEMPLATE, context)
            return filename, doc_bytes

        defense_output = DefenseOutput(
            title=f"{case_dto.cause_of_action or '民事纠纷'}答辩状",
            parties=[],
            defense_opinion=(structured.get("defense_opinion") or "答辩人不同意原告的诉讼请求"),
            defense_reasons=structured.get("defense_reason", ""),
            evidence=[],
        )
        context = service._build_defense_context(case_dto, defense_output)
        filename = service._generate_filename(case_dto.id, "defense")
        doc_bytes = service._render_template(service.DEFENSE_TEMPLATE, context)
        return filename, doc_bytes

    def _save_document(self, filename: str, doc_bytes: bytes, case_id: int) -> Any:
        from apps.litigation_ai.dependencies import get_generated_document_storage

        relative_path = get_generated_document_storage().save_for_case(
            case_id=case_id, filename=filename, content=doc_bytes
        )
        logger.info("文档已保存", extra={"filename": filename, "relative_path": relative_path})
        return relative_path
