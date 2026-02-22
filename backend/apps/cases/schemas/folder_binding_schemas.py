"""API schemas and serializers."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from .base import CaseFolderBinding, Schema, SchemaMixin, field_validator


class CaseFolderBindingCreateSchema(Schema):
    folder_path: str

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path(cls, v: Any) -> Any:
        if not v or not v.strip():
            raise ValueError(str(_("文件夹路径不能为空")))
        return v.strip()


class CaseFolderBindingResponseSchema(Schema):
    id: int
    case_id: int
    folder_path: str
    folder_path_display: str
    is_accessible: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_binding(
        cls, obj: CaseFolderBinding, is_accessible: bool = True, display_path: str | None = None
    ) -> CaseFolderBindingResponseSchema:
        return cls(
            id=obj.id,
            case_id=obj.case_id,
            folder_path=obj.folder_path,
            folder_path_display=display_path or obj.folder_path_display,
            is_accessible=is_accessible,
            created_at=SchemaMixin._resolve_datetime_iso(obj.created_at) or "",
            updated_at=SchemaMixin._resolve_datetime_iso(obj.updated_at) or "",
        )


class FolderBrowseEntrySchema(Schema):
    name: str
    path: str


class FolderBrowseResponseSchema(Schema):
    browsable: bool
    message: str | None = None
    path: str | None = None
    parent_path: str | None = None
    entries: list[FolderBrowseEntrySchema]


__all__: list[str] = [
    "CaseFolderBindingCreateSchema",
    "CaseFolderBindingResponseSchema",
    "FolderBrowseEntrySchema",
    "FolderBrowseResponseSchema",
]
