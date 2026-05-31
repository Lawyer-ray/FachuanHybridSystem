"""全局搜索 API — 跨实体关键词搜索"""

from __future__ import annotations

from typing import Any

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

@router.get("", response=GlobalSearchResult)
def global_search(request: HttpRequest, q: str = "", limit: int = 5) -> dict[str, Any]:
    if not q or len(q.strip()) < 1:
        return GlobalSearchResult().dict()

    from apps.core.services.search_service import (
        search_cases,
        search_clients,
        search_contacts,
        search_contracts,
        search_court_sms,
        search_inbox,
    )

    q = q.strip()
    limit = min(limit, 10)

    return {
        "clients": [SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_clients(q, limit)],
        "cases": [SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_cases(q, limit)],
        "contracts": [
            SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_contracts(q, limit)
        ],
        "inbox": [SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_inbox(q, limit)],
        "court_sms": [
            SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_court_sms(q, limit)
        ],
        "contacts": [SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in search_contacts(q, limit)],
    }
