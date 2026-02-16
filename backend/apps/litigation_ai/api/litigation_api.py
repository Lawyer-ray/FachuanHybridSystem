"""API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.core.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .schemas import (
    CreateSessionRequest,
    ErrorResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    MessageListResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    UpdateSessionStatusRequest,
)

logger = logging.getLogger(__name__)

router = Router(tags=["AI 诉讼文书生成"], auth=JWTOrSessionAuth())


def _get_conversation_service() -> Any:
    from apps.litigation_ai.services import LitigationConversationService

    return LitigationConversationService()


def _get_document_generator_service() -> Any:
    from apps.litigation_ai.services import DocumentGeneratorService

    return DocumentGeneratorService()


@router.post(
    "/sessions",
    response={200: SessionDetailResponse, 400: ErrorResponse, 403: ErrorResponse},
)
@rate_limit_from_settings("TASK", by_user=True)
def create_session(request: HttpRequest, payload: CreateSessionRequest) -> Any:
    service = _get_conversation_service()
    user = getattr(request, "user", None)

    session = service.create_session(case_id=payload.case_id, user_id=user.id if user else None)
    recommended_types = service.get_recommended_document_types(payload.case_id)

    return {
        "session_id": session.session_id,
        "case_id": session.case_id,
        "document_type": session.document_type,
        "status": session.status,
        "metadata": session.metadata,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [],
        "recommended_types": recommended_types,
    }


@router.get("/sessions", response={200: SessionListResponse, 403: ErrorResponse})
def list_sessions(
    request: HttpRequest, case_id: int | None = None, status: str | None = None, limit: int = 20, offset: int = 0
) -> Any:
    service = _get_conversation_service()
    user = getattr(request, "user", None)

    sessions_data = service.list_sessions(
        user_id=user.id if user else None,
        case_id=case_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"count": sessions_data["total"], "results": sessions_data["sessions"]}


@router.get(
    "/sessions/{session_id}",
    response={200: SessionDetailResponse, 404: ErrorResponse, 403: ErrorResponse},
)
def get_session(request: HttpRequest, session_id: str) -> Any:
    service = _get_conversation_service()

    session = service.get_session(session_id)
    messages = service.get_messages(session_id)
    recommended_types = service.get_recommended_document_types(session.case_id)

    return {
        "session_id": session.session_id,
        "case_id": session.case_id,
        "document_type": session.document_type,
        "status": session.status,
        "metadata": session.metadata,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
                "created_at": msg.created_at,
            }
            for msg in messages
        ],
        "recommended_types": recommended_types,
    }


@router.get(
    "/sessions/{session_id}/messages",
    response={200: MessageListResponse, 404: ErrorResponse, 403: ErrorResponse},
)
def get_messages(request: HttpRequest, session_id: str, limit: int = 50, offset: int = 0) -> Any:
    service = _get_conversation_service()

    messages = service.get_messages(session_id, limit=limit, offset=offset)
    total = service.get_message_count(session_id)

    return {
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
                "created_at": msg.created_at,
            }
            for msg in messages
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch(
    "/sessions/{session_id}",
    response={200: SessionResponse, 404: ErrorResponse, 400: ErrorResponse, 403: ErrorResponse},
)
def update_session_status(request: HttpRequest, session_id: str, payload: UpdateSessionStatusRequest) -> Any:
    service = _get_conversation_service()
    session = service.update_session_status(session_id, payload.status)

    return {
        "session_id": session.session_id,
        "case_id": session.case_id,
        "document_type": session.document_type,
        "status": session.status,
        "metadata": session.metadata,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.delete(
    "/sessions/{session_id}",
    response={204: None, 404: ErrorResponse, 403: ErrorResponse},
)
def delete_session(request: HttpRequest, session_id: str) -> Any:
    service = _get_conversation_service()
    user = getattr(request, "user", None)
    service.delete_session(session_id, user)
    return 204, None


@router.post(
    "/sessions/{session_id}/generate",
    response={200: GenerateDocumentResponse, 404: ErrorResponse, 400: ErrorResponse, 403: ErrorResponse},
)
@rate_limit_from_settings("LLM", by_user=True)
def generate_document(request: HttpRequest, session_id: str, payload: GenerateDocumentRequest) -> Any:
    service = _get_document_generator_service()

    conversation_service = _get_conversation_service()
    conversation_service.get_session(session_id)

    task = service.generate_document(session_id=session_id, template_id=payload.template_id)

    return {
        "task_id": task.id,
        "document_name": task.document_name,
        "document_url": task.document_url,
        "status": task.status,
        "created_at": task.created_at,
    }


@router.get(
    "/tasks/{task_id}",
    response={200: GenerateDocumentResponse, 404: ErrorResponse, 403: ErrorResponse},
)
def get_task_status(request: HttpRequest, task_id: int) -> Any:
    service = _get_document_generator_service()
    user = getattr(request, "user", None)
    task = service.get_task_status(task_id, user)

    return {
        "task_id": task.id,
        "document_name": task.document_name,
        "document_url": task.document_url if task.document_url else None,
        "status": task.status,
        "created_at": task.created_at,
    }
