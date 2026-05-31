"""案件工作人员联系方式 API."""

from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest
from ninja import Router

from apps.contacts.schemas import CaseContactIn, CaseContactOut, CaseContactSearchResult, CaseContactUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()

def _get_contact_service() -> Any:
    from apps.contacts.services.contact_service import CaseContactService

    return CaseContactService()

@router.get("/contacts", response=list[CaseContactOut])
def list_contacts(request: HttpRequest, case_id: int | None = None, stage: str | None = None) -> list[CaseContactOut]:
    service = _get_contact_service()
    ctx = extract_request_context(request)
    return cast(
        list[CaseContactOut],
        service.list_contacts(case_id=case_id, stage=stage, user=ctx.user),
    )

@router.post("/contacts", response=CaseContactOut)
def create_contact(request: HttpRequest, payload: CaseContactIn) -> CaseContactOut:
    service = _get_contact_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude={"case_id"})
    return cast(
        CaseContactOut,
        service.create_contact(case_id=payload.case_id, data=data, user=ctx.user),
    )

@router.get("/contacts/search", response=list[CaseContactSearchResult])
def search_contacts(
    request: HttpRequest,
    q: str | None = None,
    court: str | None = None,
    role: str | None = None,
    limit: int = 20,
) -> list[CaseContactSearchResult]:
    service = _get_contact_service()
    return cast(
        list[CaseContactSearchResult],
        service.search_contacts_public(q=q, court=court, role=role, limit=limit),
    )

@router.get("/contacts/{contact_id}", response=CaseContactOut)
def get_contact(request: HttpRequest, contact_id: int) -> CaseContactOut:
    service = _get_contact_service()
    ctx = extract_request_context(request)
    return cast(CaseContactOut, service.get_contact(contact_id=contact_id, user=ctx.user))

@router.put("/contacts/{contact_id}", response=CaseContactOut)
def update_contact(request: HttpRequest, contact_id: int, payload: CaseContactUpdate) -> CaseContactOut:
    service = _get_contact_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return cast(
        CaseContactOut,
        service.update_contact(contact_id=contact_id, data=data, user=ctx.user),
    )

@router.delete("/contacts/{contact_id}")
def delete_contact(request: HttpRequest, contact_id: int) -> Any:
    service = _get_contact_service()
    ctx = extract_request_context(request)
    return service.delete_contact(contact_id=contact_id, user=ctx.user)
