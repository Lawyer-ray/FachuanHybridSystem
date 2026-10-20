"""合同绑定文件夹浏览 API Schemas（与案件域的 CaseFolderBrowse 契约同形）。"""

from __future__ import annotations

from ninja import Schema

__all__: list[str] = [
    "ContractFolderSubfolderOut",
    "ContractFolderFileOut",
    "ContractFolderEntriesOut",
    "ContractFolderEntryNameIn",
]


class ContractFolderSubfolderOut(Schema):
    name: str
    """绑定根下的相对路径（posix，不含开头斜杠），下钻时原样回传"""

    subpath: str


class ContractFolderFileOut(Schema):
    name: str
    subpath: str
    size: int
    modified_at: str


class ContractFolderEntriesOut(Schema):
    browsable: bool
    message: str | None = None
    path_display: str = ""
    subpath: str = ""
    parent_subpath: str = ""
    folders: list[ContractFolderSubfolderOut] = []
    files: list[ContractFolderFileOut] = []


class ContractFolderEntryNameIn(Schema):
    """新建 / 重命名共用入参：subpath 定位目标（mkdir 为父目录、rename 为条目本身），name 为新名字。"""

    subpath: str = ""
    name: str
