"""全局搜索 API — 跨实体关键词搜索"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

router = Router()


class SearchResultItem(Schema):
    id: int
    title: str
    subtitle: str = ""
    # 仅当事人（clients）有值：ours=我方 / opposing=对方；其他类别恒为空串
    side: Literal["ours", "opposing", ""] = ""
    # 合同类型代码（contracts / cases 两类填充，对应 core.models.enums.CaseType）：
    # 前端按诉讼(civil/criminal/administrative/labor/intl)/非诉(special/advisor)
    # 分流详情路由 /projects/:id 或 /projects/:id/nonlit
    case_type: str = ""
    # 仅 cases 填充：所属委托合同（= 项目）的 id 与名称——项目语义下案件挂在合同分组下
    contract_id: int | None = None
    contract_name: str = ""


class GlobalSearchResult(Schema):
    clients: list[SearchResultItem] = []
    cases: list[SearchResultItem] = []
    contracts: list[SearchResultItem] = []
    inbox: list[SearchResultItem] = []
    court_sms: list[SearchResultItem] = []
    contacts: list[SearchResultItem] = []


def _to_items(raw: list[Any]) -> list[SearchResultItem]:
    return [
        SearchResultItem(
            id=r.id,
            title=r.title,
            subtitle=r.subtitle,
            side=r.side,
            case_type=r.case_type,
            contract_id=r.contract_id,
            contract_name=r.contract_name,
        )
        for r in raw
    ]


@router.get("", response=GlobalSearchResult)
async def global_search(request: HttpRequest, q: str = "", limit: int = 5) -> dict[str, Any]:  # pragma: no cover
    if not q or len(q.strip()) < 1:
        return GlobalSearchResult().dict()

    import logging

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

    logger = logging.getLogger(__name__)
    q = q.strip()
    limit = min(limit, 10)

    # 安全（第4轮审计）：搜索查询按 user/org_access 做行级过滤。
    # 纯 JWT 请求在中间件期未认证，request.org_access 为 None，
    # 这里显式补算（带缓存），避免 JWT 用户搜索退化成空结果。
    user = get_request_user(request)
    org_access = await sync_to_async(resolve_request_org_access)(request, user)

    # 6 个独立 DB 搜索并发执行，延迟降为最慢那一个
    # W2 修复：thread_sensitive=False 让每个调用在独立线程中真正并行
    #
    # return_exceptions=True 是**降级隔离**，不是吞错：任一类查询炸了（典型是
    # 模型加了字段但迁移没上、某表缺列），此前 gather 直接把异常抛出去，整个
    # 检索面板 500「啥都搜不出来」——一个坏类别连坐了另外五个好类别。
    # 现在坏的那个只让自己那类返回空（并记 ERROR 日志留痕），其余类别照常出结果。
    stf = sync_to_async(thread_sensitive=False)
    raw = await asyncio.gather(
        stf(search_clients)(q, limit, user=user, org_access=org_access),
        stf(search_cases)(q, limit, user=user, org_access=org_access),
        stf(search_contracts)(q, limit, user=user, org_access=org_access),
        stf(search_inbox)(q, limit),
        stf(search_court_sms)(q, limit, user=user, org_access=org_access),
        stf(search_contacts)(q, limit, user=user, org_access=org_access),
        return_exceptions=True,
    )

    out: dict[str, Any] = {}
    for key, result in zip(("clients", "cases", "contracts", "inbox", "court_sms", "contacts"), raw, strict=True):
        if isinstance(result, BaseException):
            logger.exception(
                "全局检索类别 %s 查询失败（该类别返回空，其余类别不受影响）：q=%r", key, q, exc_info=result
            )
            out[key] = []
        else:
            out[key] = _to_items(result)
    return out
