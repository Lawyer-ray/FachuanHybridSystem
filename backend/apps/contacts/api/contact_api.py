"""案件工作人员联系方式 API."""

from __future__ import annotations

from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.contacts.schemas import CaseContactIn, CaseContactOut, CaseContactSearchResult, CaseContactUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_contact_service() -> Any:
    from apps.contacts.services.contact_service import CaseContactService

    return CaseContactService()


@router.get("/contacts", response=list[CaseContactOut])
async def list_contacts(request: HttpRequest, case_id: int | None = None, stage: str | None = None) -> list[CaseContactOut]:  # pragma: no cover
    service = _get_contact_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> list[CaseContactOut]:
        qs = service.list_contacts(case_id=case_id, stage=stage, user=ctx.user)
        return [CaseContactOut.from_orm(c) for c in qs]

    return await _fetch()


@router.post("/contacts", response=CaseContactOut)
async def create_contact(request: HttpRequest, payload: CaseContactIn) -> CaseContactOut:  # pragma: no cover
    service = _get_contact_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude={"case_id"})

    @sync_to_async
    def _create() -> CaseContactOut:
        contact = service.create_contact(case_id=payload.case_id, data=data, user=ctx.user)
        return CaseContactOut.from_orm(contact)

    return await _create()


@router.get("/contacts/search", response=list[CaseContactSearchResult])
async def search_contacts(  # pragma: no cover
    request: HttpRequest,
    q: str | None = None,
    court: str | None = None,
    role: str | None = None,
    limit: int = 20,
) -> list[CaseContactSearchResult]:
    service = _get_contact_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> list[dict[str, Any]]:
        return service.search_contacts_public(q=q, court=court, role=role, limit=limit, user=ctx.user)

    return await _fetch()


@router.get("/contacts/{contact_id}", response=CaseContactOut)
async def get_contact(request: HttpRequest, contact_id: int) -> CaseContactOut:  # pragma: no cover
    service = _get_contact_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> CaseContactOut:
        contact = service.get_contact(contact_id=contact_id, user=ctx.user)
        return CaseContactOut.from_orm(contact)

    return await _fetch()


@router.put("/contacts/{contact_id}", response=CaseContactOut)
async def update_contact(request: HttpRequest, contact_id: int, payload: CaseContactUpdate) -> CaseContactOut:  # pragma: no cover
    service = _get_contact_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    @sync_to_async
    def _update() -> CaseContactOut:
        contact = service.update_contact(contact_id=contact_id, data=data, user=ctx.user)
        return CaseContactOut.from_orm(contact)

    return await _update()


@router.delete("/contacts/{contact_id}")
async def delete_contact(request: HttpRequest, contact_id: int) -> Any:  # pragma: no cover
    service = _get_contact_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.delete_contact)(contact_id=contact_id, user=ctx.user)
