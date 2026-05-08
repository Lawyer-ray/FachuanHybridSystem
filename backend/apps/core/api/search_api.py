"""全局搜索 API — 跨实体关键词搜索"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet
from django.http import HttpRequest
from ninja import Router, Schema

router = Router()


class SearchResultItem(Schema):
    id: int
    title: str
    subtitle: str = ""


class GlobalSearchResult(Schema):
    clients: list[SearchResultItem] = []
    cases: list[SearchResultItem] = []
    contracts: list[SearchResultItem] = []
    inbox: list[SearchResultItem] = []
    court_sms: list[SearchResultItem] = []
    contacts: list[SearchResultItem] = []


def _search_clients(q: str, limit: int) -> list[SearchResultItem]:
    from apps.client.models import Client

    qs: QuerySet = Client.objects.filter(
        Q(name__icontains=q) | Q(phone__icontains=q) | Q(id_number__icontains=q)
    ).distinct()[:limit]
    return [
        SearchResultItem(id=c.id, title=c.name, subtitle=c.phone or "")
        for c in qs
    ]


def _search_cases(q: str, limit: int) -> list[SearchResultItem]:
    from apps.cases.models import Case

    qs: QuerySet = Case.objects.filter(
        Q(name__icontains=q)
        | Q(case_numbers__number__icontains=q)
        | Q(parties__client__name__icontains=q)
    ).distinct()[:limit]
    results: list[SearchResultItem] = []
    for c in qs:
        case_number = ""
        first_number = c.case_numbers.first()
        if first_number:
            case_number = first_number.number
        results.append(SearchResultItem(id=c.id, title=c.name or "", subtitle=case_number))
    return results


def _search_contracts(q: str, limit: int) -> list[SearchResultItem]:
    from apps.contracts.models import Contract

    qs: QuerySet = Contract.objects.filter(
        Q(name__icontains=q) | Q(contract_parties__client__name__icontains=q)
    ).distinct()[:limit]
    return [
        SearchResultItem(id=c.id, title=c.name or "", subtitle="")
        for c in qs
    ]


def _search_inbox(q: str, limit: int) -> list[SearchResultItem]:
    from apps.message_hub.models import InboxMessage

    qs: QuerySet = InboxMessage.objects.filter(
        Q(subject__icontains=q) | Q(sender__icontains=q)
    ).order_by("-received_at")[:limit]
    return [
        SearchResultItem(
            id=m.id,
            title=m.subject or "(无主题)",
            subtitle=m.sender or "",
        )
        for m in qs
    ]


def _search_court_sms(q: str, limit: int) -> list[SearchResultItem]:
    from apps.automation.models import CourtSMS

    qs: QuerySet = CourtSMS.objects.filter(
        Q(content__icontains=q) | Q(case__name__icontains=q)
    ).order_by("-received_at")[:limit]
    results: list[SearchResultItem] = []
    for sms in qs:
        preview = sms.content[:50] + ("..." if len(sms.content) > 50 else "")
        case_name = sms.case.name if sms.case else ""
        results.append(SearchResultItem(id=sms.id, title=preview, subtitle=case_name))
    return results


def _search_contacts(q: str, limit: int) -> list[SearchResultItem]:
    from apps.contacts.models import CaseContact

    qs: QuerySet = CaseContact.objects.filter(
        Q(name__icontains=q) | Q(phone__icontains=q) | Q(authority__name__icontains=q)
    ).distinct()[:limit]
    results: list[SearchResultItem] = []
    for contact in qs:
        role_display = contact.get_role_display()
        authority_name = contact.authority.name if contact.authority else ""
        subtitle = f"{role_display} | {authority_name}" if authority_name else role_display
        results.append(SearchResultItem(id=contact.id, title=contact.name, subtitle=subtitle))
    return results


@router.get("", response=GlobalSearchResult)
def global_search(request: HttpRequest, q: str = "", limit: int = 5) -> dict[str, Any]:
    if not q or len(q.strip()) < 1:
        return GlobalSearchResult().dict()

    q = q.strip()
    limit = min(limit, 10)

    return {
        "clients": _search_clients(q, limit),
        "cases": _search_cases(q, limit),
        "contracts": _search_contracts(q, limit),
        "inbox": _search_inbox(q, limit),
        "court_sms": _search_court_sms(q, limit),
        "contacts": _search_contacts(q, limit),
    }
