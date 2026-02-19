"""
案件当事人 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any, cast

from ninja import Router

from apps.core.request_context import extract_request_context

from apps.cases.schemas import CasePartyIn, CasePartyOut, CasePartyUpdate

router = Router()


def _get_case_party_service() -> Any:
    """工厂函数：创建 CasePartyService 实例"""
    from apps.cases.services.case_party_service import CasePartyService

    return CasePartyService()


@router.get("/parties", response=list[CasePartyOut])
def list_parties(request: Any, case_id: int | None = None) -> list[CasePartyOut]:
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return cast(list[CasePartyOut], service.list_parties(case_id=case_id, user=ctx.user))


@router.post("/parties", response=CasePartyOut)
def create_party(request: Any, payload: CasePartyIn) -> CasePartyOut:
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return cast(
        CasePartyOut,
        service.create_party(
            case_id=payload.case_id, client_id=payload.client_id, legal_status=payload.legal_status, user=ctx.user
        ),
    )


@router.get("/parties/{party_id}", response=CasePartyOut)
def get_party(request: Any, party_id: int) -> CasePartyOut:
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return cast(CasePartyOut, service.get_party(party_id=party_id, user=ctx.user))


@router.put("/parties/{party_id}", response=CasePartyOut)
def update_party(request: Any, party_id: int, payload: CasePartyUpdate) -> CasePartyOut:
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    data = payload.dict(exclude_unset=True)
    return cast(CasePartyOut, service.update_party(party_id=party_id, data=data, user=ctx.user))


@router.delete("/parties/{party_id}")
def delete_party(request: Any, party_id: int) -> Any:
    service = _get_case_party_service()
    ctx = extract_request_context(request)
    return service.delete_party(party_id=party_id, user=ctx.user)
