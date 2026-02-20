"""External service client."""

from typing import cast

from apps.client.models import Client
from apps.core.interfaces import ClientDTO


class ClientDtoAssembler:
    def to_dto(self, client: Client) -> ClientDTO:
        return ClientDTO(
            id=cast(int, client.pk), # type: ignore
            name=client.name,
            client_type=client.client_type,
            phone=client.phone,
            id_number=client.id_number if hasattr(client, "id_number") else None,
            address=client.address if hasattr(client, "address") else None,
            is_our_client=client.is_our_client,
        )
