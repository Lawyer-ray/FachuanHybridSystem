"""按名称解析 OA 当事人：复用本地 Client，缺失时按调用方给定阵营自动创建。

律所ID 同步（新建合同页）用：OA「客户信息」tab 的委托人才是我方当事人，利冲表
里的其他相关方（含共同被告 / 共同原告、第三人）都不是——``is_our_client`` 只由
调用方按分组传入，本服务不做阵营判断，也不改写非我方分组的既有标记（同一当事人
可能在别的案件里是我方委托人，全局标记不能因一次同步被抹掉）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.client.models import Client

logger = logging.getLogger("apps.client")

# 名称里出现这些词按法人 / 非法人组织建库，否则按自然人（OA 利冲表不带主体类型）
_LEGAL_ENTITY_MARKERS: tuple[str, ...] = (
    "公司",
    "集团",
    "企业",
    "合伙企业",
    "事务所",
    "研究院",
    "银行",
    "医院",
    "学校",
    "中心",
    "合作社",
    "协会",
    "基金会",
    "委员会",
    "政府",
    "管理局",
    "法院",
    "检察院",
)

_VALID_CLIENT_TYPES = {str(value) for value, _ in Client.CLIENT_TYPE_CHOICES}


@dataclass(frozen=True)
class ResolvedParty:
    """本地 Client 解析结果。"""

    client_id: int
    name: str
    created: bool


class ClientPartyResolveService:
    """名称 → Client；本地没有且允许创建时自动建库。"""

    def resolve(
        self,
        *,
        name: str,
        is_our_client: bool,
        allow_create: bool = True,
        client_type: str | None = None,
        id_number: str = "",
        phone: str = "",
        address: str = "",
        legal_representative: str = "",
    ) -> ResolvedParty | None:
        """按名称（或证件号）解析 Client，返回 None 表示本地无记录且不允许创建。

        我方分组的既有记录若标记为「非我方」，会同步改为「我方」——否则
        ContractParty.save() 会把委托人身份自动纠正成对方当事人。
        """
        name = (name or "").strip()
        if not name:
            return None

        client = self._find(name=name, id_number=id_number)
        if client is None:
            if not allow_create:
                return None
            client = self._create(
                name=name,
                is_our_client=is_our_client,
                client_type=client_type,
                id_number=id_number,
                phone=phone,
                address=address,
                legal_representative=legal_representative,
            )
            if client is None:
                return None
            return ResolvedParty(client_id=client.pk, name=client.name, created=True)

        self._promote_our_client(client, is_our_client=is_our_client)
        return ResolvedParty(client_id=client.pk, name=client.name, created=False)

    def _find(self, *, name: str, id_number: str) -> Client | None:
        """证件号优先（唯一键），其次名称精确匹配（忽略大小写）。"""
        id_number = (id_number or "").strip()
        if id_number:
            client = Client.objects.filter(id_number=id_number).first()
            if client is not None:
                return client
        return Client.objects.filter(name__iexact=name).order_by("pk").first()

    def _promote_our_client(self, client: Client, *, is_our_client: bool) -> None:
        if not is_our_client or client.is_our_client:
            return
        client.is_our_client = True
        client.save(update_fields=["is_our_client", "updated_at"])
        logger.info("OA 同步将既有当事人标记为我方: client_id=%s", client.pk)

    def _create(
        self,
        *,
        name: str,
        is_our_client: bool,
        client_type: str | None,
        id_number: str,
        phone: str,
        address: str,
        legal_representative: str,
    ) -> Client | None:
        try:
            with transaction.atomic():
                return Client.objects.create(
                    name=name[:255],
                    client_type=self._normalize_client_type(client_type, name),
                    is_our_client=is_our_client,
                    id_number=(id_number or "").strip() or None,
                    phone=(phone or "").strip(),
                    address=(address or "").strip(),
                    legal_representative=(legal_representative or "").strip(),
                )
        except Exception:
            logger.warning("OA 同步自动创建当事人失败: %s", name, exc_info=True)
            return None

    def _normalize_client_type(self, client_type: str | None, name: str) -> str:
        candidate = str(client_type or "").strip()
        if candidate in _VALID_CLIENT_TYPES:
            return candidate
        if any(marker in name for marker in _LEGAL_ENTITY_MARKERS):
            return str(Client.LEGAL)
        return str(Client.NATURAL)
