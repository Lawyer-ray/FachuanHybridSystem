"""案件绑定文件夹浏览的 API schemas。"""

from __future__ import annotations

from .base import Schema

__all__: list[str] = [
    "CaseFolderSubfolderSchema",
    "CaseFolderFileSchema",
    "CaseFolderEntriesResponseSchema",
    "CaseFolderEntryNameIn",
]


class CaseFolderSubfolderSchema(Schema):
    name: str
    """绑定根下的相对路径（posix，不含开头斜杠），下钻时原样回传"""

    subpath: str


class CaseFolderFileSchema(Schema):
    name: str
    subpath: str
    size: int
    modified_at: str


class CaseFolderEntriesResponseSchema(Schema):
    browsable: bool
    message: str | None = None
    path_display: str = ""
    subpath: str = ""
    parent_subpath: str = ""
    folders: list[CaseFolderSubfolderSchema] = []
    files: list[CaseFolderFileSchema] = []


class CaseFolderEntryNameIn(Schema):
    """新建 / 重命名共用入参：subpath 定位目标（mkdir 为父目录、rename 为条目本身），name 为新名字。"""

    subpath: str = ""
    name: str
