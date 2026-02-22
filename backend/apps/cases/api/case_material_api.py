"""API endpoints."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import (
    CaseMaterialBindCandidateOut,
    CaseMaterialBindIn,
    CaseMaterialGroupOrderIn,
    CaseMaterialUploadOut,
)
from apps.cases.services import CaseLogService
from apps.cases.services.material.wiring import build_case_material_service
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security import get_request_access_context

router = Router()


def _get_case_material_service() -> Any:
    return build_case_material_service()


def _get_caselog_service() -> CaseLogService:
    return CaseLogService()


@router.get("/{case_id}/materials/bind-candidates", response=list[CaseMaterialBindCandidateOut])
def list_bind_candidates(request: HttpRequest, case_id: int) -> Any:
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return service.list_bind_candidates(
        case_id=case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/{case_id}/materials/bind")
@rate_limit_from_settings("TASK", by_user=True)
def bind_materials(request: HttpRequest, case_id: int, payload: CaseMaterialBindIn) -> dict[str, int]:
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    items: list[dict[str, Any]] = [x.model_dump() for x in payload.items]
    saved = service.bind_materials(
        case_id=case_id,
        items=items,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"saved_count": len(saved)}


@router.post("/{case_id}/materials/group-order")
@rate_limit_from_settings("TASK", by_user=True)
def save_group_order(request: HttpRequest, case_id: int, payload: CaseMaterialGroupOrderIn) -> dict[str, bool]:
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    service.save_group_order(
        case_id=case_id,
        category=payload.category,
        ordered_type_ids=payload.ordered_type_ids,
        side=payload.side,
        supervising_authority_id=payload.supervising_authority_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"ok": True}


@router.post("/{case_id}/materials/upload", response=CaseMaterialUploadOut)
@rate_limit_from_settings("UPLOAD", by_user=True)
def upload_materials(request: HttpRequest, case_id: int) -> dict[str, Any]:
    service = _get_caselog_service()
    ctx = get_request_access_context(request)
    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []
    log = service.create_log(  # type: ignore[call-arg, call-arg]
        case_id=case_id,
        content="上传材料",
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    created = service.upload_attachments(
        log_id=log.id,
        files=files,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"log_id": log.id, "attachment_ids": [x.id for x in created]}  # type: ignore[attr-defined]
