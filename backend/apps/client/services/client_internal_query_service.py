"""当事人内部查询服务。"""

from __future__ import annotations

from apps.client.models import Client, ClientIdentityDoc, PropertyClue


class ClientInternalQueryService:
    def get_client(self, *, client_id: int) -> Client | None:
        return Client.objects.prefetch_related("identity_docs").filter(id=client_id).first()

    def get_clients_by_ids(self, *, client_ids: list[int]) -> list[Client]:
        if not client_ids:
            return []
        clients: list[Client] = list(Client.objects.filter(id__in=client_ids))
        client_map: dict[int, Client] = {c.id: c for c in clients}
        return [client_map[cid] for cid in client_ids if cid in client_map]

    def get_client_by_name(self, *, name: str) -> Client | None:
        return Client.objects.filter(name=name).first()

    def list_all_clients(self) -> list[Client]:
        return list(Client.objects.order_by("id"))

    def search_clients_by_name(self, *, name: str, exact_match: bool = False) -> list[Client]:
        if not name:
            return []
        if exact_match:
            qs = Client.objects.filter(name=name)
        else:
            qs = Client.objects.filter(name__icontains=name)
        return list(qs)

    def list_property_clues_by_client(self, *, client_id: int) -> list[PropertyClue]:
        return list(PropertyClue.objects.filter(client_id=client_id))

    def is_natural_person(self, *, client_id: int) -> bool:
        client_type: str | None = Client.objects.filter(id=client_id).values_list("client_type", flat=True).first()
        return bool(client_type == Client.NATURAL)

    def list_identity_docs_by_client(self, *, client_id: int) -> list[ClientIdentityDoc]:
        return list(ClientIdentityDoc.objects.filter(client_id=client_id))
