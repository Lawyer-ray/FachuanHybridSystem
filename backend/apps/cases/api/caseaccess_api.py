"""
案件访问授权 API

同步端点由 Django Ninja 自动包装到线程池执行，ORM 访问安全。
"""

from __future__ import annotations

from typing import Any

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
def list_grants(  # pragma: no cover
    request: HttpRequest, case_id: int | None = None, grantee_id: int | None = None
) -> Any:
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    return service.list_grants(
        case_id=case_id,
        grantee_id=grantee_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/grants", response=CaseAccessGrantOut)
def create_grant(request: HttpRequest, payload: CaseAccessGrantIn) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    return service.create_grant(
        case_id=payload.case_id,
        grantee_id=payload.grantee_id,
        user=ctx.user,
    )


@router.get("/grants/{grant_id}", response=CaseAccessGrantOut)
def get_grant(request: HttpRequest, grant_id: int) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    return service.get_grant(
        grant_id=grant_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.put("/grants/{grant_id}", response=CaseAccessGrantOut)
def update_grant(request: HttpRequest, grant_id: int, payload: CaseAccessGrantUpdate) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return service.update_grant(
        grant_id=grant_id,
        data=data,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete("/grants/{grant_id}")
def delete_grant(request: HttpRequest, grant_id: int) -> Any:  # pragma: no cover
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    return service.delete_grant(
        grant_id=grant_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
