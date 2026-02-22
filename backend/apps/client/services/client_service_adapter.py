"""当事人服务适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ClientDTO, IClientService

if TYPE_CHECKING:
    from apps.client.models import Client
    from apps.core.dtos import ClientIdentityDocDTO, PropertyClueDTO

    from .client_dto_assembler import ClientDtoAssembler, ClientRelatedDtoAssembler
    from .client_internal_query_service import ClientInternalQueryService


class ClientServiceAdapter(IClientService):
    def __init__(
        self,
        dto_assembler: ClientDtoAssembler | None = None,
        internal_query_service: ClientInternalQueryService | None = None,
        related_dto_assembler: ClientRelatedDtoAssembler | None = None,
    ) -> None:
        self._dto_assembler = dto_assembler
        self._internal_query_service = internal_query_service
        self._related_dto_assembler = related_dto_assembler

    @property
    def dto_assembler(self) -> ClientDtoAssembler:
        if self._dto_assembler is None:
            from .client_dto_assembler import ClientDtoAssembler

            self._dto_assembler = ClientDtoAssembler()
        return self._dto_assembler

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
        if self._internal_query_service is None:
            from .client_internal_query_service import ClientInternalQueryService

            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    @property
    def related_dto_assembler(self) -> ClientRelatedDtoAssembler:
        if self._related_dto_assembler is None:
            from .client_dto_assembler import ClientRelatedDtoAssembler

            self._related_dto_assembler = ClientRelatedDtoAssembler()
        return self._related_dto_assembler

    def _to_dto(self, client: Client) -> ClientDTO:
        return self.dto_assembler.to_dto(client)

    def get_client(self, client_id: int) -> ClientDTO | None:
        client = self.internal_query_service.get_client(client_id=client_id)
        return self._to_dto(client) if client else None

    def get_client_internal(self, client_id: int) -> ClientDTO | None:
        return self.get_client(client_id)

    def get_clients_by_ids(self, client_ids: list[int]) -> list[ClientDTO]:
        clients = self.internal_query_service.get_clients_by_ids(client_ids=client_ids)
        return [self._to_dto(c) for c in clients]

    def validate_client_exists(self, client_id: int) -> bool:
        return self.internal_query_service.get_client(client_id=client_id) is not None

    def get_client_by_name(self, name: str) -> ClientDTO | None:
        client = self.internal_query_service.get_client_by_name(name=name)
        return self._to_dto(client) if client else None

    def get_all_clients_internal(self) -> list[ClientDTO]:
        clients = self.internal_query_service.list_all_clients()
        return [self._to_dto(client) for client in clients]

    def search_clients_by_name_internal(self, name: str, exact_match: bool = False) -> list[ClientDTO]:
        clients = self.internal_query_service.search_clients_by_name(name=name, exact_match=exact_match)
        return [self._to_dto(client) for client in clients]

    def get_property_clues_by_client_internal(self, client_id: int) -> list[PropertyClueDTO]:
        clues = self.internal_query_service.list_property_clues_by_client(client_id=client_id)
        return self.related_dto_assembler.property_clues_to_dtos(clues)

    def is_natural_person_internal(self, client_id: int) -> bool:
        return self.internal_query_service.is_natural_person(client_id=client_id)

    def get_identity_docs_by_client_internal(self, client_id: int) -> list[ClientIdentityDocDTO]:
        docs = self.internal_query_service.list_identity_docs_by_client(client_id=client_id)
        return self.related_dto_assembler.identity_docs_to_dtos(docs)
