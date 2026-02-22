"""
Contract Schemas - Folder Binding

文件夹绑定相关的 Schema 定义.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema
from pydantic import field_validator

from apps.contracts.models import ContractFolderBinding


class FolderBindingCreateSchema(Schema):
    """创建文件夹绑定请求 Schema"""

    folder_path: str

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path(cls, v: Any) -> Any:
        """验证文件夹路径不为空"""
        if not v or not v.strip():
            raise ValueError("文件夹路径不能为空")
        return v.strip()


class FolderBindingResponseSchema(Schema):
    """文件夹绑定响应 Schema"""

    id: int
    contract_id: int
    folder_path: str
    folder_path_display: str  # 格式化后的显示路径
    created_at: datetime
    updated_at: datetime
    is_accessible: bool  # 文件夹是否可访问

    @staticmethod
    def from_binding(
        obj: ContractFolderBinding, is_accessible: bool = True, display_path: str | None = None
    ) -> FolderBindingResponseSchema:
        """从 ContractFolderBinding 对象创建 Schema"""
        return FolderBindingResponseSchema(
            id=obj.id,
            contract_id=obj.contract_id,
            folder_path=obj.folder_path,
            folder_path_display=display_path or obj.folder_path,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            is_accessible=is_accessible,
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
