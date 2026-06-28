"""API schemas and serializers."""

from __future__ import annotations

from typing import ClassVar

from .base import CaseParty, ClientOut, ModelSchema, Schema


class CasePartyIn(Schema):
    case_id: int
    client_id: int
    legal_status: str | None = None


class CasePartyUpdate(Schema):
    case_id: int | None = None
    client_id: int | None = None
    legal_status: str | None = None


class CasePartyOut(ModelSchema):
    client_detail: ClientOut

    class Meta:
        model = CaseParty
        fields: ClassVar = ["id", "case", "client", "legal_status"]

    @staticmethod
    def resolve_client_detail(obj: Any) -> ClientOut:
        # When called from from_orm(), obj is the Django model instance
        # When called from model_validate() via DjangoGetter, obj is the raw
        # dict/Pydantic model returned by the view.
        if isinstance(obj, dict):
            client = obj.get("client_detail") or obj.get("client")
        else:
            client = getattr(obj, "client_detail", None) or getattr(obj, "client", None)
        if isinstance(client, ClientOut):
            return client
        if isinstance(client, dict):
            return ClientOut(**client)
        # Fallback: obj is a Django model instance with a client FK
        return ClientOut.from_model(client)

    @staticmethod
    def resolve_legal_status(obj: Any) -> str | None:
        # When called from model_validate(), obj may not have get_legal_status_display
        if hasattr(obj, "get_legal_status_display"):
            return obj.get_legal_status_display() if obj.legal_status else None
        # For dict input
        if isinstance(obj, dict):
            return obj.get("legal_status")
        return getattr(obj, "legal_status", None)


class CasePartyCreate(Schema):
    client_id: int
    legal_status: str | None = None


__all__: list[str] = [
    "CasePartyCreate",
    "CasePartyIn",
    "CasePartyOut",
    "CasePartyUpdate",
]
