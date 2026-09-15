"""API endpoints."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import (
    CaseMaterialAttachmentsDeleteIn,
    CaseMaterialAttachmentsDeleteOut,
    CaseMaterialBindCandidateOut,
    CaseMaterialBindIn,
    CaseMaterialDeleteAllIn,
    CaseMaterialDeleteAllOut,
    CaseMaterialDeleteOut,
    CaseMaterialGroupOrderIn,
    CaseMaterialGroupRenameIn,
    CaseMaterialGroupRenameOut,
    CaseMaterialReplaceIn,
    CaseMaterialReplaceOut,
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
async def list_bind_candidates(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return await asyncio.to_thread(
        service.list_bind_candidates,
        case_id=case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/{case_id}/materials/bind")
@rate_limit_from_settings("TASK", by_user=True)
async def bind_materials(
    request: HttpRequest, case_id: int, payload: CaseMaterialBindIn
) -> dict[str, int]:  # pragma: no cover
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    items: list[dict[str, Any]] = [x.model_dump() for x in payload.items]
    saved = await asyncio.to_thread(
        service.bind_materials,
        case_id=case_id,
        items=items,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"saved_count": len(saved)}


@router.post("/{case_id}/materials/group-order")
@rate_limit_from_settings("TASK", by_user=True)
async def save_group_order(
    request: HttpRequest, case_id: int, payload: CaseMaterialGroupOrderIn
) -> dict[str, bool]:  # pragma: no cover
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    await asyncio.to_thread(
        service.save_group_order,
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
async def upload_materials(request: HttpRequest, case_id: int) -> dict[str, Any]:  # pragma: no cover
    service = _get_caselog_service()
    ctx = get_request_access_context(request)
    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []

    def _do_upload() -> dict[str, Any]:
        log = service.create_log(
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
        return {"log_id": log.id, "attachment_ids": [x.id for x in created]}

    return await asyncio.to_thread(_do_upload)


@router.post(
    "/{case_id}/materials/{material_id}/replace",
    response=CaseMaterialReplaceOut,
)
@rate_limit_from_settings("TASK", by_user=True)
async def replace_material_file(  # pragma: no cover
    request: HttpRequest, case_id: int, material_id: int, payload: CaseMaterialReplaceIn
) -> dict[str, Any]:
    """替换材料对应的附件文件。"""
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return await asyncio.to_thread(
        service.replace_material_file,
        case_id=case_id,
        material_id=material_id,
        new_attachment_id=payload.new_attachment_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post(
    "/{case_id}/materials/group-rename",
    response=CaseMaterialGroupRenameOut,
)
@rate_limit_from_settings("TASK", by_user=True)
async def rename_group(
    request: HttpRequest, case_id: int, payload: CaseMaterialGroupRenameIn
) -> dict[str, Any]:  # pragma: no cover
    """重命名材料分组。"""
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return await asyncio.to_thread(
        service.rename_group,
        case_id=case_id,
        type_id=payload.type_id,
        new_type_name=payload.new_type_name,
        update_global=payload.update_global,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete(
    "/{case_id}/materials/attachments",
    response=CaseMaterialAttachmentsDeleteOut,
)
@rate_limit_from_settings("TASK", by_user=True)
async def delete_attachments(
    request: HttpRequest, case_id: int, payload: CaseMaterialAttachmentsDeleteIn
) -> dict[str, Any]:  # pragma: no cover
    """批量删除未绑定材料的附件（含物理文件）。"""
    service = _get_case_material_service()
    ctx = get_request_access_context(request)

    def _delete() -> dict[str, Any]:
        return cast(
            dict[str, Any],
            service.delete_attachments(
                case_id=case_id,
                attachment_ids=payload.attachment_ids,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            ),
        )

    return await sync_to_async(_delete)()


@router.delete(
    "/{case_id}/materials/{material_id}",
    response=CaseMaterialDeleteOut,
)
@rate_limit_from_settings("TASK", by_user=True)
async def delete_material(request: HttpRequest, case_id: int, material_id: int) -> dict[str, Any]:  # pragma: no cover
    """删除材料绑定（附件文件不受影响）。"""
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return await asyncio.to_thread(
        service.delete_material,
        case_id=case_id,
        material_id=material_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete(
    "/{case_id}/materials",
    response=CaseMaterialDeleteAllOut,
)
@rate_limit_from_settings("TASK", by_user=True)
async def delete_all_materials(
    request: HttpRequest, case_id: int, payload: CaseMaterialDeleteAllIn
) -> dict[str, Any]:  # pragma: no cover
    """按分类删除案件下的所有材料。"""
    service = _get_case_material_service()
    ctx = get_request_access_context(request)
    return await asyncio.to_thread(
        service.delete_all_materials,
        case_id=case_id,
        category=payload.category,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
