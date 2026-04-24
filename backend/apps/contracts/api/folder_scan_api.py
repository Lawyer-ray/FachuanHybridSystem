"""合同文件夹自动捕获 API。"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest
from ninja import Router

from apps.contracts.schemas import (
    ContractFolderScanConfirmIn,
    ContractFolderScanConfirmOut,
    ContractFolderScanStartIn,
    ContractFolderScanStartOut,
    ContractFolderScanStatusOut,
    ContractFolderScanSubfolderListOut,
)
from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security import get_request_access_context

router = Router()


def _get_service() -> ContractFolderScanService:
    return ContractFolderScanService()


def _require_contract_access(request: HttpRequest, contract_id: int) -> None:
    from apps.contracts.services.contract import wiring

    ctx = get_request_access_context(request)
    wiring.get_contract_query_facade().get_contract_ctx(contract_id=contract_id, ctx=ctx)


@router.post("/{contract_id}/folder-scan", response=ContractFolderScanStartOut)
@rate_limit_from_settings("TASK", by_user=True)
def start_contract_scan(request: HttpRequest, contract_id: int, payload: ContractFolderScanStartIn) -> dict[str, str]:
    _require_contract_access(request, contract_id)
    ctx = get_request_access_context(request)

    session = _get_service().start_scan(
        contract_id=contract_id,
        started_by=ctx.user,
        rescan=bool(payload.rescan),
        scan_subfolder=str(payload.scan_subfolder or ""),
    )
    return {
        "session_id": str(session.id),
        "status": str(session.status),
        "task_id": str(session.task_id or ""),
    }


@router.get("/{contract_id}/folder-scan/subfolders", response=ContractFolderScanSubfolderListOut)
def list_contract_scan_subfolders(request: HttpRequest, contract_id: int) -> dict[str, object]:
    _require_contract_access(request, contract_id)
    return _get_service().list_scan_subfolders(contract_id=contract_id)


@router.get("/{contract_id}/folder-scan/latest", response=ContractFolderScanStatusOut)
def get_latest_contract_scan(request: HttpRequest, contract_id: int) -> dict[str, object]:
    """返回合同最新的扫描会话状态；无会话时返回空状态。"""
    _require_contract_access(request, contract_id)
    service = _get_service()
    session = service.get_latest_session(contract_id=contract_id)
    if session is None:
        return {
            "session_id": "",
            "status": "",
            "progress": 0,
            "current_file": "",
            "summary": {"total_files": 0, "deduped_files": 0, "classified_files": 0},
            "candidates": [],
            "error_message": "",
            "archive_category": "",
            "archive_item_options": [],
            "work_log_suggestions": [],
        }
    return service.build_status_payload(session=session)


@router.get("/{contract_id}/folder-scan/{session_id}", response=ContractFolderScanStatusOut)
def get_contract_scan_status(request: HttpRequest, contract_id: int, session_id: UUID) -> dict[str, object]:
    _require_contract_access(request, contract_id)

    service = _get_service()
    session = service.get_session(contract_id=contract_id, session_id=session_id)
    return service.build_status_payload(session=session)


@router.post("/{contract_id}/folder-scan/{session_id}/confirm", response=ContractFolderScanConfirmOut)
@rate_limit_from_settings("TASK", by_user=True)
def confirm_contract_scan(
    request: HttpRequest,
    contract_id: int,
    session_id: UUID,
    payload: ContractFolderScanConfirmIn,
) -> dict[str, object]:
    _require_contract_access(request, contract_id)

    return _get_service().confirm_import(
        contract_id=contract_id,
        session_id=session_id,
        items=[item.model_dump() for item in payload.items],
        work_log_suggestions=[item.model_dump() for item in payload.work_log_suggestions],
    )
