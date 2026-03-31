"""当事人 DTO 组装器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.dto import ClientIdentityDocDTO, PropertyClueDTO
from apps.core.interfaces import ClientDTO

if TYPE_CHECKING:
    from apps.client.models import Client, ClientIdentityDoc, PropertyClue


class ClientDtoAssembler:
    """当事人基础 DTO 组装。"""

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


class ClientRelatedDtoAssembler:
    """当事人关联对象 DTO 组装。"""

    def property_clue_to_dto(self, clue: PropertyClue) -> PropertyClueDTO:
        return PropertyClueDTO(
            id=clue.pk,
            client_id=clue.client_id,
            clue_type=clue.clue_type,
            content=clue.content,
            description=None,
        )

    def property_clues_to_dtos(self, clues: list[PropertyClue]) -> list[PropertyClueDTO]:
        return [self.property_clue_to_dto(c) for c in clues]

    def identity_doc_to_dto(self, doc: ClientIdentityDoc) -> ClientIdentityDocDTO:
        return ClientIdentityDocDTO(
            id=doc.pk,
            client_id=doc.client_id,
            doc_type=doc.doc_type,
            doc_type_display=doc.get_doc_type_display(),
            file_path=doc.media_url,
            expiry_date=str(doc.expiry_date) if doc.expiry_date else None,
            is_valid=True,
        )

    def identity_docs_to_dtos(self, docs: list[ClientIdentityDoc]) -> list[ClientIdentityDocDTO]:
        return [self.identity_doc_to_dto(d) for d in docs]
