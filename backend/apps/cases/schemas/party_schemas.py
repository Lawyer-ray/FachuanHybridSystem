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
    def resolve_client_detail(obj: CaseParty) -> ClientOut:
        return ClientOut.from_model(obj.client)

    @staticmethod
    def resolve_legal_status(obj: CaseParty) -> str | None:
        return obj.get_legal_status_display() if obj.legal_status else None


class CasePartyCreate(Schema):
    client_id: int
    legal_status: str | None = None


__all__: list[str] = [
    "CasePartyCreate",
    "CasePartyIn",
    "CasePartyOut",
    "CasePartyUpdate",
]
