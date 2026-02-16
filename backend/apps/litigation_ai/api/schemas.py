"""API schemas and serializers."""

from datetime import datetime
from typing import Any

from ninja import Schema


class CreateSessionRequest(Schema):
    case_id: int


class SessionResponse(Schema):
    session_id: str
    case_id: int
    document_type: str | None = None
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SessionListResponse(Schema):
    count: int
    results: list[dict[str, Any]]


class MessageResponse(Schema):
    id: int
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime


class SessionDetailResponse(Schema):
    session_id: str
    case_id: int
    document_type: str | None = None
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
    recommended_types: list[str]


class MessageListResponse(Schema):
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int


class UpdateSessionStatusRequest(Schema):
    status: str


class GenerateDocumentRequest(Schema):
    template_id: int | None = None


class GenerateDocumentResponse(Schema):
    task_id: int
    document_name: str | None = None
    document_url: str | None = None
    status: str
    created_at: datetime


class ErrorResponse(Schema):
    message: str
    code: str
    errors: dict[str, Any] | None = None
