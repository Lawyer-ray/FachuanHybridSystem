"""当事人内部查询服务。"""

from __future__ import annotations

import time

from apps.client.models import Client, ClientIdentityDoc, PropertyClue

# 模块级缓存：用于 list_all_clients
_client_cache: list[Client] | None = None
_client_cache_time: float = 0
_client_cache_ttl: int = 300  # 缓存有效期 5 分钟（可调）


class ClientInternalQueryService:
    def get_client(self, *, client_id: int) -> Client | None:  # pragma: no cover
        return Client.objects.prefetch_related("identity_docs").filter(id=client_id).first()

    def get_clients_by_ids(self, *, client_ids: list[int]) -> list[Client]:
        if not client_ids:
            return []
        clients: list[Client] = list(Client.objects.prefetch_related("identity_docs").filter(id__in=client_ids))
        client_map: dict[int, Client] = {c.id: c for c in clients}
        return [client_map[cid] for cid in client_ids if cid in client_map]

    def get_client_by_name(self, *, name: str) -> Client | None:  # pragma: no cover
        return Client.objects.prefetch_related("identity_docs").filter(name=name).first()

    def list_all_clients(self) -> list[Client]:  # pragma: no cover
        global _client_cache, _client_cache_time
        now = time.time()
        if _client_cache is None or (now - _client_cache_time) > _client_cache_ttl:
            _client_cache = list(Client.objects.prefetch_related("identity_docs").order_by("id"))
            _client_cache_time = now
        return _client_cache

    def search_clients_by_name(self, *, name: str, exact_match: bool = False) -> list[Client]:
        if not name:
            return []
        qs = Client.objects.prefetch_related("identity_docs")
        if exact_match:
            qs = qs.filter(name=name)
        else:
            qs = qs.filter(name__icontains=name)
        return list(qs)

    def list_property_clues_by_client(self, *, client_id: int) -> list[PropertyClue]:  # pragma: no cover
        return list(PropertyClue.objects.prefetch_related("attachments").filter(client_id=client_id))

    def is_natural_person(self, *, client_id: int) -> bool:  # pragma: no cover
        client_type: str | None = Client.objects.filter(id=client_id).values_list("client_type", flat=True).first()
        return bool(client_type == Client.NATURAL)

    def list_identity_docs_by_client(self, *, client_id: int) -> list[ClientIdentityDoc]:  # pragma: no cover
        return list(ClientIdentityDoc.objects.filter(client_id=client_id))
