"""合同绑定文件夹浏览 API Schemas（与案件域的 CaseFolderBrowse 契约同形）。"""

from __future__ import annotations

from ninja import Schema

__all__: list[str] = [
    "ContractFolderSubfolderOut",
    "ContractFolderFileOut",
    "ContractFolderEntriesOut",
    "ContractFolderEntryNameIn",
    "ContractFolderCopyIn",
    "ContractFolderPathIn",
]


class ContractFolderSubfolderOut(Schema):
    name: str
    """绑定根下的相对路径（posix，不含开头斜杠），下钻时原样回传"""

    subpath: str
    """子目录下**一层**文件数；前端据此判断常法「服务事项是否已交付」"""
    file_count: int = 0


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


class ContractFolderCopyIn(Schema):
    """复制入参：subpath 为复制源，dest_subpath 为目标目录（空 = 绑定根）。"""

    subpath: str
    dest_subpath: str = ""


class ContractFolderPathIn(Schema):
    """删除入参：subpath 定位要移入回收目录的条目。"""

    subpath: str


class ContractFolderSaveIn(Schema):
    """原地保存入参：subpath 定位文件，expect_mtime 做乐观锁。

    content 走 multipart 字段 `file`（二进制不能塞 JSON），mtime 走表单字段。
    单独定 schema 只为说明语义边界：这是**覆盖写**，与上传的「不覆盖」相反。
    """

    subpath: str
    # 打开时该文件的 mtime（秒）。缺省不校验——只在明确要防并发时传。
    expect_mtime: float | None = None


class ContractFolderSaveOut(Schema):
    """保存结果：新 subpath/文件名/大小/mtime（前端据此更新状态）。"""

    subpath: str
    name: str
    size: int = 0
    modified_at: str | None = None
