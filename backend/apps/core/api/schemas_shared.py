"""Module for schemas shared."""

from datetime import datetime
from typing import Any

from ninja import Schema

from apps.core.schemas import SchemaMixin

__all__: list[str] = [
    "ClientIdentityDocLiteOut",
    "ClientLiteOut",
]


class ClientIdentityDocLiteOut(Schema):
    doc_type: str
    file_path: str
    uploaded_at: datetime
    media_url: str | None = None

    @classmethod
    def from_model(cls, obj: Any) -> "ClientIdentityDocLiteOut":
        return cls(
            doc_type=getattr(obj, "doc_type", ""),
            file_path=getattr(obj, "file_path", ""),
            uploaded_at=obj.uploaded_at,
            media_url=obj.media_url if hasattr(obj, "media_url") else None,
        )


class ClientLiteOut(SchemaMixin, Schema):
    id: int
    name: str
    is_our_client: bool
    phone: str | None = None
    address: str | None = None
    client_type: str
    id_number: str | None = None
    legal_representative: str | None = None
    legal_representative_id_number: str | None = None
    client_type_label: str
    identity_docs: list[ClientIdentityDocLiteOut]

    @classmethod
    def from_model(cls, obj: Any) -> "ClientLiteOut":
        docs: list[ClientIdentityDocLiteOut] = []
        identity_docs = getattr(obj, "identity_docs", None)
        if identity_docs is not None and hasattr(identity_docs, "all"):
            docs = [ClientIdentityDocLiteOut.from_model(item) for item in identity_docs.all()]

        return cls(
            id=obj.id,
            name=getattr(obj, "name", ""),
            is_our_client=bool(getattr(obj, "is_our_client", False)),
            phone=getattr(obj, "phone", None),
            address=getattr(obj, "address", None),
            client_type=getattr(obj, "client_type", ""),
            id_number=getattr(obj, "id_number", None),
            legal_representative=getattr(obj, "legal_representative", None),
            legal_representative_id_number=getattr(obj, "legal_representative_id_number", None),
            client_type_label=SchemaMixin._get_display(obj, "client_type") or "",
            identity_docs=docs,
        )
