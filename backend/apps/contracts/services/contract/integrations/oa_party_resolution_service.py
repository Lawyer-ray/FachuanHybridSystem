"""律所ID 同步：回填 JSON 的当事人名单 → 本地 Client id（缺失按阵营自动建库）。

``build_sync_payload`` 只产出名单；本服务把名单落到本地当事人库，供前端直接勾选
inline 行。阵营口径只有一条：**OA「客户信息」tab 的委托人才是我方当事人**；
利冲表里的对立方、同案其他当事人（共同被告 / 共同原告等）与第三人都不是，
自动建库时 ``is_our_client=False``。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.client.services.client_party_resolve_service import ClientPartyResolveService

logger = logging.getLogger("apps.contracts")

# (payload 分组, 是否我方当事人)；四组条目统一用 customer_type 传客户主体类型（可能缺省）
_GROUP_RULES: tuple[tuple[str, bool], ...] = (
    ("clients", True),
    ("opponents", False),
    ("co_parties", False),
    ("third_parties", False),
)


class OaPartyResolutionService:
    """把同步 payload 里四组当事人解析成 Client id；单个失败不中断整体同步。"""

    def __init__(self, client_party_resolve_service: ClientPartyResolveService | None = None) -> None:
        self._client_parties = client_party_resolve_service or ClientPartyResolveService()

    def resolve_payload(self, payload: dict[str, Any], *, allow_create: bool) -> dict[str, Any]:
        """原地为每组条目补 client_id / client_name / created，并返回同一 dict。"""
        for group, is_our_client in _GROUP_RULES:
            items = payload.get(group) or []
            payload[group] = [
                self._resolve_item(item, is_our_client=is_our_client, allow_create=allow_create) for item in items
            ]
        return payload

    def _resolve_item(
        self,
        item: dict[str, Any],
        *,
        is_our_client: bool,
        allow_create: bool,
    ) -> dict[str, Any]:
        name = str(item.get("name") or "").strip()
        if not name:
            return {**item, "client_id": None, "client_name": "", "created": False}

        resolved = self._client_parties.resolve(
            name=name,
            is_our_client=is_our_client,
            allow_create=allow_create,
            client_type=str(item.get("customer_type") or ""),
            id_number=str(item.get("id_number") or ""),
            phone=str(item.get("phone") or ""),
            address=str(item.get("address") or ""),
            legal_representative=str(item.get("legal_representative") or ""),
        )
        if resolved is None:
            return {**item, "client_id": None, "client_name": name, "created": False}
        return {
            **item,
            "client_id": resolved.client_id,
            "client_name": resolved.name,
            "created": resolved.created,
        }
