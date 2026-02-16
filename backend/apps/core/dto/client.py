"""Module for client."""

from dataclasses import dataclass
from typing import Any


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
    def from_model(cls, client: Any) -> "ClientDTO":
        return cls(
            id=client.id,
            name=client.name,
            client_type=client.client_type if hasattr(client, "client_type") else "individual",
            phone=client.phone if hasattr(client, "phone") else None,
            id_number=client.id_number if hasattr(client, "id_number") else None,
            address=client.address if hasattr(client, "address") else None,
            is_our_client=client.is_our_client if hasattr(client, "is_our_client") else False,
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
    def from_model(cls, doc: Any) -> "ClientIdentityDocDTO":
        return cls(
            id=doc.id,
            client_id=doc.client_id,
            doc_type=doc.doc_type,
            doc_type_display=doc.get_doc_type_display(),
            file_path=doc.file.url if doc.file else None,
            expiry_date=str(doc.expiry_date) if doc.expiry_date else None,
            is_valid=doc.is_valid if hasattr(doc, "is_valid") else True,
        )
