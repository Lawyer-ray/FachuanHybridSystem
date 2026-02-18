"""Module for client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.client.models import Client, ClientIdentityDoc


@dataclass
class ClientDTO:
    id: int
    name: str
    client_type: str
    phone: str | None = None
    id_number: str | None = None
    address: str | None = None
    is_our_client: bool = False

    @classmethod
    def from_model(cls, client: Client) -> ClientDTO:
        return cls(
            id=client.id,
            name=client.name,
            client_type=client.client_type,
            phone=client.phone,
            id_number=client.id_number,
            address=client.address,
            is_our_client=client.is_our_client,
        )


@dataclass
class PropertyClueDTO:
    id: int
    client_id: int
    clue_type: str
    content: str
    description: str | None = None


@dataclass
class ClientIdentityDocDTO:
    id: int
    client_id: int
    doc_type: str
    doc_type_display: str
    file_path: str | None = None
    expiry_date: str | None = None
    is_valid: bool = True

    @classmethod
    def from_model(cls, doc: ClientIdentityDoc) -> ClientIdentityDocDTO:
        return cls(
            id=doc.id,
            client_id=doc.client_id,
            doc_type=doc.doc_type,
            doc_type_display=doc.get_doc_type_display(),
            file_path=doc.media_url(),
        )
