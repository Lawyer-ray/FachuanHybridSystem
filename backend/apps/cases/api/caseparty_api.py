"""
案件当事人 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CasePartyIn, CasePartyOut, CasePartyUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_case_party_service() -> Any:
    """工厂函数：创建 CasePartyService 实例"""
    from apps.cases.services.party.case_party_service import CasePartyService

    return CasePartyService()


@router.get("/parties", response=list[CasePartyOut])
async def list_parties(request: HttpRequest, case_id: int | None = None) -> list[CasePartyOut]:  # pragma: no cover
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.list_parties)(  # type: ignore[no-any-return]
        case_id=case_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
    )


@router.post("/parties", response=CasePartyOut)
async def create_party(request: HttpRequest, payload: CasePartyIn) -> CasePartyOut:  # pragma: no cover
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.create_party)(  # type: ignore[no-any-return]
        case_id=payload.case_id, client_id=payload.client_id, legal_status=payload.legal_status,
        user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
    )


@router.get("/parties/{party_id}", response=CasePartyOut)
async def get_party(request: HttpRequest, party_id: int) -> CasePartyOut:  # pragma: no cover
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.get_party)(  # type: ignore[no-any-return]
        party_id=party_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
    )


@router.put("/parties/{party_id}", response=CasePartyOut)
async def update_party(request: HttpRequest, party_id: int, payload: CasePartyUpdate) -> CasePartyOut:  # pragma: no cover
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return await sync_to_async(service.update_party)(  # type: ignore[no-any-return]
        party_id=party_id, data=data, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
    )


@router.delete("/parties/{party_id}")
async def delete_party(request: HttpRequest, party_id: int) -> Any:  # pragma: no cover
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.delete_party)(
        party_id=party_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
    )
