"""案件文件夹自动捕获 API。"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import (
    CaseFolderScanStageIn,
    CaseFolderScanStageOut,
    CaseFolderScanStartIn,
    CaseFolderScanStartOut,
    CaseFolderScanStatusOut,
    CaseFolderScanSubfolderListOut,
)
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.services.case.case_query_service import CaseQueryService
from apps.cases.services.material.folder_scan_service import CaseFolderScanService
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security import get_request_access_context

router = Router()


def _get_service() -> CaseFolderScanService:
    return CaseFolderScanService()


def _require_case_access(request: HttpRequest, case_id: int) -> None:
    ctx = get_request_access_context(request)
    CaseQueryService(access_policy=CaseAccessPolicy()).get_case(
        case_id=case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/{case_id}/folder-scan", response=CaseFolderScanStartOut)
@rate_limit_from_settings("TASK", by_user=True)
def start_case_scan(request: HttpRequest, case_id: int, payload: CaseFolderScanStartIn) -> dict[str, str]:
    _require_case_access(request, case_id)
    ctx = get_request_access_context(request)

    session = _get_service().start_scan(
        case_id=case_id,
        started_by=ctx.user,
        rescan=bool(payload.rescan),
        scan_subfolder=str(payload.scan_subfolder or ""),
        enable_recognition=bool(payload.enable_recognition),
    )
    return {
        "session_id": str(session.id),
        "status": str(session.status),
        "task_id": str(session.task_id or ""),
    }


@router.get("/{case_id}/folder-scan/subfolders", response=CaseFolderScanSubfolderListOut)
def list_case_scan_subfolders(request: HttpRequest, case_id: int) -> dict[str, object]:
    _require_case_access(request, case_id)
    return _get_service().list_scan_subfolders(case_id=case_id)


@router.get("/{case_id}/folder-scan/{session_id}", response=CaseFolderScanStatusOut)
def get_case_scan_status(request: HttpRequest, case_id: int, session_id: UUID) -> dict[str, object]:
    _require_case_access(request, case_id)

    service = _get_service()
    session = service.get_session(case_id=case_id, session_id=session_id)
    return service.build_status_payload(session=session)


@router.post("/{case_id}/folder-scan/{session_id}/stage", response=CaseFolderScanStageOut)
@rate_limit_from_settings("TASK", by_user=True)
def stage_case_scan(
    request: HttpRequest,
    case_id: int,
    session_id: UUID,
    payload: CaseFolderScanStageIn,
) -> dict[str, object]:
    _require_case_access(request, case_id)
    ctx = get_request_access_context(request)

    return _get_service().stage_to_attachments(
        case_id=case_id,
        session_id=session_id,
        items=[item.model_dump() for item in payload.items],
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
