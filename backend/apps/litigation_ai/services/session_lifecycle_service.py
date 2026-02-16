"""Business logic services."""

from __future__ import annotations

"""
会话生命周期服务

负责会话的创建、查询、更新状态、删除等生命周期管理.
从 LitigationConversationSessionService 中拆分出来.
"""


import logging
from typing import Any

from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException

from .session_shared import SessionDTO

logger = logging.getLogger("apps.litigation_ai")


class SessionLifecycleService:
    """会话生命周期服务 - 管理会话的创建、查询、状态更新和删除"""

    def __init__(self) -> None:
        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository
        from apps.litigation_ai.services.wiring import get_case_service, get_conversation_history_service

        self.case_service = get_case_service()
        self.conversation_history_service = get_conversation_history_service()
        self.session_repo = LitigationSessionRepository()

    def create_session(self, case_id: int, user_id: int | None = None) -> SessionDTO:
        from apps.litigation_ai.models import LitigationSession

        session = LitigationSession.objects.create(
            case_id=case_id,
            user_id=user_id,
            status="active",
            metadata={},
        )
        return self._to_session_dto(session)

    def get_session(self, session_id: str) -> SessionDTO:
        session = self.session_repo.get_session_with_case_sync(session_id)
        if not session:
            raise NotFoundError(
                message="会话不存在",
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )
        return self._to_session_dto(session)

    @transaction.atomic
    def update_session_status(
        self, session_id: str, status: str, metadata_updates: dict[str, Any] | None = None
    ) -> SessionDTO:
        from apps.litigation_ai.models.choices import SessionStatus

        session = self.session_repo.get_session_sync(session_id)
        if not session:
            raise NotFoundError(
                message="会话不存在",
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        valid_statuses = [choice[0] for choice in SessionStatus.choices]
        if status not in valid_statuses:
            raise ValidationException(
                message="无效的状态",
                code="INVALID_STATUS",
                errors={"status": f"状态必须是 {valid_statuses} 之一"},
            )

        session.status = status
        if metadata_updates:
            session.metadata.update(metadata_updates)
        session.save()
        return self._to_session_dto(session)

    def get_recommended_document_types(self, case_id: int) -> list[str]:
        from apps.core.enums import LegalStatus
        from apps.litigation_ai.models.choices import DocumentType
        from apps.litigation_ai.services.wiring import get_court_pleading_signals_service

        case = self.case_service.get_case_internal(case_id)
        if not case:
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            )

        parties = self.case_service.get_case_parties_internal(case_id)
        our_legal_statuses = [p.legal_status for p in parties if p.legal_status]

        signals = get_court_pleading_signals_service().get_signals_internal(case_id)

        plaintiff_like = {
            LegalStatus.PLAINTIFF,
            LegalStatus.APPLICANT,
            LegalStatus.APPELLANT,
            LegalStatus.ORIGINAL_PLAINTIFF,
        }
        defendant_like = {
            LegalStatus.DEFENDANT,
            LegalStatus.RESPONDENT,
            LegalStatus.APPELLEE,
            LegalStatus.ORIGINAL_DEFENDANT,
            LegalStatus.CRIMINAL_DEFENDANT,
        }

        recommended_types: list[str] = []
        for legal_status in our_legal_statuses:
            if legal_status in plaintiff_like:
                if DocumentType.COMPLAINT not in recommended_types:
                    recommended_types.append(DocumentType.COMPLAINT)
                if signals.has_counterclaim and DocumentType.COUNTERCLAIM_DEFENSE not in recommended_types:
                    recommended_types.append(DocumentType.COUNTERCLAIM_DEFENSE)
            elif legal_status in defendant_like:
                if DocumentType.DEFENSE not in recommended_types:
                    recommended_types.append(DocumentType.DEFENSE)
                if DocumentType.COUNTERCLAIM not in recommended_types:
                    recommended_types.append(DocumentType.COUNTERCLAIM)

        return recommended_types

    def list_sessions(
        self,
        user_id: int | None = None,
        case_id: int | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if user_id:
            filters["user_id"] = user_id
        if case_id:
            filters["case_id"] = case_id
        if status:
            filters["status"] = status

        total_count, sessions = self.session_repo.list_sessions_sync(filters=filters, limit=limit, offset=offset)
        message_counts = self.conversation_history_service.count_messages_by_litigation_session_ids_internal(
            litigation_session_ids=[s.id for s in sessions]
        )

        results: list[Any] = []
        for session in sessions:
            results.append(
                {
                    "session_id": str(session.session_id),
                    "case_id": session.case_id,
                    "document_type": session.document_type,
                    "status": session.status,
                    "metadata": session.metadata,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "message_count": message_counts.get(session.id, 0),
                }
            )

        return {"sessions": results, "total": total_count, "limit": limit, "offset": offset}

    @transaction.atomic
    def delete_session(self, session_id: str, user: Any | None = None) -> None:
        from apps.core.exceptions import PermissionDenied

        session = self.session_repo.get_session_for_update_sync(session_id)
        if not session:
            raise NotFoundError(
                message="会话不存在",
                code="SESSION_NOT_FOUND",
                errors={"session_id": f"会话 {session_id} 不存在"},
            )

        if user and session.user_id != user.id:
            raise PermissionDenied(message="无权限删除此会话", code="PERMISSION_DENIED")

        from django.db import IntegrityError, connection

        self._detach_related_rows(session)
        try:
            session.delete()
        except IntegrityError:
            violations: list[Any] = []
            if connection.vendor == "sqlite":
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_key_check")
                    violations = cursor.fetchall() or []

            logger.error(
                "删除会话失败:外键约束阻止删除",
                extra={
                    "session_id": str(session.session_id),
                    "case_id": session.case_id,
                    "fk_violations": violations[:20],
                },
                exc_info=True,
            )
            raise

    def _detach_related_rows(self, session: Any) -> None:
        from django.db import models

        related_objects: list[Any] = getattr(session._meta, "related_objects", []) or []
        for rel in related_objects:
            field = getattr(rel, "field", None)
            if field is None:
                continue
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue

            model = rel.related_model
            field_name = field.name
            qs = model._default_manager.filter(**{field_name: session})
            if not qs.exists():
                continue

            if getattr(field, "null", False):
                qs.update(**{field_name: None})
            else:
                qs.delete()

        self._detach_legacy_tables(session)

    def _detach_legacy_tables(self, session: Any) -> None:
        from django.db import connection

        if connection.vendor != "sqlite":
            return

        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_litigationmessage';")
            exists = cursor.fetchone()
            if not exists:
                return
            cursor.execute("DELETE FROM documents_litigationmessage WHERE session_id = %s", [session.id])

    def _to_session_dto(self, session: Any) -> SessionDTO:
        return SessionDTO(
            id=session.id,
            session_id=str(session.session_id),
            case_id=session.case_id,
            case_name=getattr(session.case, "name", "") if getattr(session, "case", None) else "",
            user_id=session.user_id,
            document_type=session.document_type or "",
            status=session.status,
            metadata=session.metadata or {},
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
