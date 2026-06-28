"""
案件访问授权 API

异步端点，Service 层同步调用通过 sync_to_async 包装。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseAccessGrantIn, CaseAccessGrantOut, CaseAccessGrantUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_case_access_service() -> Any:
    """工厂函数：创建 CaseAccessService 实例"""
    from apps.cases.services.case.case_access_service import CaseAccessService

    return CaseAccessService()


@router.get("/grants", response=list[CaseAccessGrantOut])
async def list_grants(  # pragma: no cover
    request: HttpRequest, case_id: int | None = None, grantee_id: int | None = None
) -> Any:
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> list[CaseAccessGrantOut]:
        qs = service.list_grants(
            case_id=case_id,
            grantee_id=grantee_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return [CaseAccessGrantOut.from_orm(g) for g in qs]

    return await _fetch()


@router.post("/grants", response=CaseAccessGrantOut)
async def create_grant(request: HttpRequest, payload: CaseAccessGrantIn) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _create() -> CaseAccessGrantOut:
        grant = service.create_grant(
            case_id=payload.case_id,
            grantee_id=payload.grantee_id,
            user=ctx.user,
        )
        return CaseAccessGrantOut.from_orm(grant)

    return await _create()


@router.get("/grants/{grant_id}", response=CaseAccessGrantOut)
async def get_grant(request: HttpRequest, grant_id: int) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> CaseAccessGrantOut:
        grant = service.get_grant(
            grant_id=grant_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return CaseAccessGrantOut.from_orm(grant)

    return await _fetch()


@router.put("/grants/{grant_id}", response=CaseAccessGrantOut)
async def update_grant(request: HttpRequest, grant_id: int, payload: CaseAccessGrantUpdate) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    @sync_to_async
    def _update() -> CaseAccessGrantOut:
        grant = service.update_grant(
            grant_id=grant_id,
            data=data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return CaseAccessGrantOut.from_orm(grant)

    return await _update()


@router.delete("/grants/{grant_id}")
async def delete_grant(request: HttpRequest, grant_id: int) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.delete_grant)(
        grant_id=grant_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
