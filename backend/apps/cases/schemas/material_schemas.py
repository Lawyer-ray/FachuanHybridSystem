"""API schemas and serializers."""

from __future__ import annotations

from typing import ClassVar

from .base import Schema, datetime


class CaseMaterialBindingOut(Schema):
    id: int
    category: str
    type_id: int | None = None
    type_name: str
    side: str | None = None
    party_ids: ClassVar[list[int]] = []
    supervising_authority_id: int | None = None


class CaseMaterialBindCandidateOut(Schema):
    attachment_id: int
    file_name: str
    file_url: str
    uploaded_at: datetime
    log_id: int
    log_created_at: datetime | None = None
    actor_name: str
    material: CaseMaterialBindingOut | None = None


class CaseMaterialBindItemIn(Schema):
    attachment_id: int
    category: str
    type_id: int | None = None
    type_name: str
    side: str | None = None
    party_ids: ClassVar[list[int]] = []
    supervising_authority_id: int | None = None


class CaseMaterialBindIn(Schema):
    items: list[CaseMaterialBindItemIn]


class CaseMaterialGroupOrderIn(Schema):
    category: str
    ordered_type_ids: list[int]
    side: str | None = None
    supervising_authority_id: int | None = None


class CaseMaterialUploadOut(Schema):
    log_id: int
    attachment_ids: list[int]


__all__: list[str] = [
    "CaseMaterialBindCandidateOut",
    "CaseMaterialBindIn",
    "CaseMaterialBindItemIn",
    "CaseMaterialBindingOut",
    "CaseMaterialGroupOrderIn",
    "CaseMaterialUploadOut",
]
