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


class CaseMaterialReplaceIn(Schema):
    """替换材料文件请求"""

    new_attachment_id: int


class CaseMaterialReplaceOut(Schema):
    """替换材料文件响应"""

    material_id: int
    old_attachment_id: int
    new_attachment_id: int


class CaseMaterialGroupRenameIn(Schema):
    """重命名材料分组请求"""

    type_id: int
    new_type_name: str
    update_global: bool = False


class CaseMaterialGroupRenameOut(Schema):
    """重命名材料分组响应"""

    type_id: int
    old_type_name: str
    new_type_name: str


class CaseMaterialDeleteOut(Schema):
    """删除材料响应"""

    material_id: int
    deleted: bool


class CaseMaterialDeleteAllIn(Schema):
    """按分类批量删除材料请求"""

    category: str


class CaseMaterialDeleteAllOut(Schema):
    """按分类批量删除材料响应"""

    category: str
    deleted_count: int


__all__: list[str] = [
    "CaseMaterialBindCandidateOut",
    "CaseMaterialBindIn",
    "CaseMaterialBindItemIn",
    "CaseMaterialBindingOut",
    "CaseMaterialDeleteAllIn",
    "CaseMaterialDeleteAllOut",
    "CaseMaterialDeleteOut",
    "CaseMaterialGroupOrderIn",
    "CaseMaterialGroupRenameIn",
    "CaseMaterialGroupRenameOut",
    "CaseMaterialReplaceIn",
    "CaseMaterialReplaceOut",
    "CaseMaterialUploadOut",
]
