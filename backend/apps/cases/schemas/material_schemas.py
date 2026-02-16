"""API schemas and serializers."""

from typing import ClassVar, Optional

from .base import Optional, Schema, datetime


class CaseMaterialBindingOut(Schema):
    id: int
    category: str
    type_id: Optional[int] = None
    type_name: str
    side: Optional[str] = None
    party_ids: ClassVar[list[int]] = []
    supervising_authority_id: Optional[int] = None


class CaseMaterialBindCandidateOut(Schema):
    attachment_id: int
    file_name: str
    file_url: str
    uploaded_at: datetime
    log_id: int
    log_created_at: Optional[datetime] = None
    actor_name: str
    material: Optional[CaseMaterialBindingOut] = None


class CaseMaterialBindItemIn(Schema):
    attachment_id: int
    category: str
    type_id: Optional[int] = None
    type_name: str
    side: Optional[str] = None
    party_ids: ClassVar[list[int]] = []
    supervising_authority_id: Optional[int] = None


class CaseMaterialBindIn(Schema):
    items: list[CaseMaterialBindItemIn]


class CaseMaterialGroupOrderIn(Schema):
    category: str
    ordered_type_ids: list[int]
    side: Optional[str] = None
    supervising_authority_id: Optional[int] = None


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
