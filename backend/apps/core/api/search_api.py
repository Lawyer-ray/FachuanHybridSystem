"""全局搜索 API — 跨实体关键词搜索"""

from __future__ import annotations

import asyncio
from typing import Any

from asgiref.sync import sync_to_async
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


def _to_items(raw: list[Any]) -> list[SearchResultItem]:
    return [SearchResultItem(id=r.id, title=r.title, subtitle=r.subtitle) for r in raw]


@router.get("", response=GlobalSearchResult)
async def global_search(request: HttpRequest, q: str = "", limit: int = 5) -> dict[str, Any]:  # pragma: no cover
    if not q or len(q.strip()) < 1:
        return GlobalSearchResult().dict()

    from apps.core.dependencies.business import resolve_request_org_access
    from apps.core.security.admin_access import get_request_user
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

    # 安全（第4轮审计）：搜索查询按 user/org_access 做行级过滤。
    # 纯 JWT 请求在中间件期未认证，request.org_access 为 None，
    # 这里显式补算（带缓存），避免 JWT 用户搜索退化成空结果。
    user = get_request_user(request)
    org_access = await sync_to_async(resolve_request_org_access)(request, user)

    # 6 个独立 DB 搜索并发执行，延迟降为最慢那一个
    # W2 修复：thread_sensitive=False 让每个调用在独立线程中真正并行
    stf = sync_to_async(thread_sensitive=False)
    clients_raw, cases_raw, contracts_raw, inbox_raw, court_sms_raw, contacts_raw = await asyncio.gather(
        stf(search_clients)(q, limit, user=user, org_access=org_access),
        stf(search_cases)(q, limit, user=user, org_access=org_access),
        stf(search_contracts)(q, limit, user=user, org_access=org_access),
        stf(search_inbox)(q, limit),
        stf(search_court_sms)(q, limit, user=user, org_access=org_access),
        stf(search_contacts)(q, limit, user=user, org_access=org_access),
    )

    return {
        "clients": _to_items(clients_raw),
        "cases": _to_items(cases_raw),
        "contracts": _to_items(contracts_raw),
        "inbox": _to_items(inbox_raw),
        "court_sms": _to_items(court_sms_raw),
        "contacts": _to_items(contacts_raw),
    }
