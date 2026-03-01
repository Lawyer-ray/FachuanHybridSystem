"""模拟庭审 API Schema."""

from datetime import datetime
from typing import Any

from ninja import Schema


class CreateMockTrialSessionRequest(Schema):
    case_id: int


class MockTrialSessionResponse(Schema):
    session_id: str
    case_id: int
    session_type: str
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MockTrialSessionDetailResponse(MockTrialSessionResponse):
    messages: list[dict[str, Any]] = []


class MockTrialSessionListResponse(Schema):
    count: int
    results: list[dict[str, Any]]


class MockTrialReportResponse(Schema):
    session_id: str
    mode: str
    report: dict[str, Any]


class ErrorResponse(Schema):
    detail: str = ""
    message: str = ""
    code: str = ""
