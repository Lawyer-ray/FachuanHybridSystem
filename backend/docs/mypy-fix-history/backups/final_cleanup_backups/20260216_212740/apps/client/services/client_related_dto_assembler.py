"""External service client."""

from typing import Any, cast

from apps.client.models import ClientIdentityDoc, PropertyClue
from apps.core.dtos import ClientIdentityDocDTO, PropertyClueDTO


class ClientRelatedDtoAssembler:
    def property_clue_to_dto(self, clue: PropertyClue) -> PropertyClueDTO:
        return PropertyClueDTO(
            id=cast(int, clue.pk),
            client_id=cast(int, clue.client_id),
            clue_type=clue.clue_type,
            content=clue.content,
            description=None,
        )

    def property_clues_to_dtos(self, clues: list[PropertyClue]) -> list[PropertyClueDTO]:
        return [self.property_clue_to_dto(c) for c in clues]

    def identity_doc_to_dto(self, doc: ClientIdentityDoc) -> ClientIdentityDocDTO:
        return ClientIdentityDocDTO(
            id=cast(int, doc.pk),
            client_id=cast(int, doc.client_id),
            doc_type=doc.doc_type,
            doc_type_display=cast(str, doc.get_doc_type_display()),
            file_path=doc.media_url(),
            expiry_date=str(doc.expiry_date) if doc.expiry_date else None,
            is_valid=True,
        )

    def identity_docs_to_dtos(self, docs: list[ClientIdentityDoc]) -> list[ClientIdentityDocDTO]:
        return [self.identity_doc_to_dto(d) for d in docs]
