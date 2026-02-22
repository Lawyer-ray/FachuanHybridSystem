"""当事人 DTO 组装器。"""

from __future__ import annotations

from apps.client.models import Client
from apps.core.interfaces import ClientDTO


class ClientDtoAssembler:
    def to_dto(self, client: Client) -> ClientDTO:
        return ClientDTO(
            id=client.id,
            name=client.name,
            client_type=client.client_type,
            phone=client.phone,
            id_number=client.id_number,
            address=client.address,
            is_our_client=client.is_our_client,
        )
