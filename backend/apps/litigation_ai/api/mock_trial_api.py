"""模拟庭审 REST API."""

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.core.auth import JWTOrSessionAuth
from apps.core.infrastructure.throttling import rate_limit_from_settings

from .mock_trial_schemas import (
    CreateMockTrialSessionRequest,
    ErrorResponse,
    MockTrialReportResponse,
    MockTrialSessionDetailResponse,
    MockTrialSessionListResponse,
    MockTrialSessionResponse,
)

logger = logging.getLogger(__name__)

router = Router(tags=["模拟庭审"], auth=JWTOrSessionAuth())


def _get_service() -> Any:
    from apps.litigation_ai.services import LitigationConversationService

    return LitigationConversationService()


@router.post(
    "/sessions",
    response={200: MockTrialSessionDetailResponse, 400: ErrorResponse, 403: ErrorResponse},
)
@rate_limit_from_settings("TASK", by_user=True)
def create_session(request: HttpRequest, payload: CreateMockTrialSessionRequest) -> Any:
    user = getattr(request, "user", None)
    session = _get_service().create_session(
        case_id=payload.case_id,
        user_id=user.id if user else None,
        session_type="mock_trial",
    )
    return {
        "session_id": str(session.session_id),
        "case_id": session.case_id,
        "session_type": "mock_trial",
        "status": session.status,
        "metadata": session.metadata,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [],
    }


@router.get("/sessions", response={200: MockTrialSessionListResponse, 403: ErrorResponse})
def list_sessions(request: HttpRequest, case_id: int | None = None, limit: int = 20, offset: int = 0) -> Any:
    service = _get_service()
    user = getattr(request, "user", None)
    data = service.list_sessions(
        user_id=user.id if user else None,
        case_id=case_id,
        session_type="mock_trial",
        limit=limit,
        offset=offset,
    )
    return {"count": data["total"], "results": data["sessions"]}


@router.get(
    "/sessions/{session_id}",
    response={200: MockTrialSessionDetailResponse, 404: ErrorResponse},
)
def get_session(request: HttpRequest, session_id: str) -> Any:
    service = _get_service()
    session = service.get_session(session_id)
    messages = service.get_messages(session_id)
    return {
        "session_id": session.session_id,
        "case_id": session.case_id,
        "session_type": "mock_trial",
        "status": session.status,
        "metadata": session.metadata,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "metadata": m.metadata, "created_at": m.created_at}
            for m in messages
        ],
    }


@router.get(
    "/sessions/{session_id}/report",
    response={200: MockTrialReportResponse, 404: ErrorResponse},
)
def get_report(request: HttpRequest, session_id: str) -> Any:
    from asgiref.sync import async_to_sync

    from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

    report_data = async_to_sync(MockTrialReportService().get_report)(session_id)
    return {
        "session_id": session_id,
        "mode": report_data.get("mode", ""),
        "report": report_data,
    }


@router.delete(
    "/sessions/{session_id}",
    response={204: None, 404: ErrorResponse},
)
def delete_session(request: HttpRequest, session_id: str) -> Any:
    service = _get_service()
    user = getattr(request, "user", None)
    service.delete_session(session_id, user)
    return 204, None


@router.get(
    "/sessions/{session_id}/export",
    response={200: None, 404: ErrorResponse, 500: ErrorResponse},
)
@rate_limit_from_settings("EXPORT", by_user=True)
def export_report(request: HttpRequest, session_id: str) -> Any:
    """导出模拟庭审报告为Word文档."""
    from asgiref.sync import async_to_sync
    from pathlib import Path

    from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService
    from apps.litigation_ai.services.mock_trial.export_service import MockTrialExportService

    # 获取报告数据
    report_data = async_to_sync(MockTrialReportService().get_report)(session_id)
    if not report_data:
        return 404, {"message": "报告不存在"}

    # 获取案件信息
    from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

    repo = LitigationSessionRepository()
    session = repo.get_session_sync(session_id)
    if not session:
        return 404, {"message": "会话不存在"}

    from apps.litigation_ai.services.wiring import get_case_service

    case_dto = get_case_service().get_case(session.case_id)
    if not case_dto:
        return 404, {"message": "案件不存在"}

    case_name = case_dto.name or ""
    case_info = {
        "case_name": case_name,
        "cause_of_action": case_dto.cause_of_action or "",
    }

    # 生成导出文件
    export_service = MockTrialExportService()
    try:
        file_path = export_service.export_to_docx(
            session_id=session_id,
            report_data=report_data,
            case_info=case_info,
        )

        # 读取文件并返回
        from django.http import FileResponse

        response = FileResponse(
            Path(file_path).open("rb"),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="模拟庭审报告_{case_name}.docx"'
        return response
    except Exception as e:
        logger.error(f"导出报告失败: {e}", exc_info=True)
        return 500, {"message": f"导出失败: {e}"}
